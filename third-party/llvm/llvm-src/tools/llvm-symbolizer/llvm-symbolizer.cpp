//===-- llvm-symbolizer.cpp - Simple addr2line-like symbolizer ------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// This utility works much like "addr2line". It is able of transforming
// tuples (module name, module offset) to code locations (function name,
// file, line number, column number). It is targeted for compiler-rt tools
// (especially AddressSanitizer and ThreadSanitizer) that can use it
// to symbolize stack traces in their error reports.
//
//===----------------------------------------------------------------------===//

#include "Opts.inc"
#include "llvm/ADT/StringExtras.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/Config/config.h"
#include "llvm/DebugInfo/Symbolize/DIPrinter.h"
#include "llvm/DebugInfo/Symbolize/Markup.h"
#include "llvm/DebugInfo/Symbolize/MarkupFilter.h"
#include "llvm/DebugInfo/Symbolize/SymbolizableModule.h"
#include "llvm/DebugInfo/Symbolize/Symbolize.h"
#include "llvm/Debuginfod/BuildIDFetcher.h"
#include "llvm/Debuginfod/Debuginfod.h"
#include "llvm/Debuginfod/HTTPClient.h"
#include "llvm/Option/Arg.h"
#include "llvm/Option/ArgList.h"
#include "llvm/Option/Option.h"
#include "llvm/Support/COM.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/Debug.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/InitLLVM.h"
#include "llvm/Support/Path.h"
#include "llvm/Support/StringSaver.h"
#include "llvm/Support/WithColor.h"
#include "llvm/Support/raw_ostream.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>

using namespace llvm;
using namespace symbolize;

namespace {
enum ID {
  OPT_INVALID = 0, // This is not an option ID.
#define OPTION(PREFIX, NAME, ID, KIND, GROUP, ALIAS, ALIASARGS, FLAGS, PARAM,  \
               HELPTEXT, METAVAR, VALUES)                                      \
  OPT_##ID,
#include "Opts.inc"
#undef OPTION
};

#define PREFIX(NAME, VALUE)                                                    \
  static constexpr StringLiteral NAME##_init[] = VALUE;                        \
  static constexpr ArrayRef<StringLiteral> NAME(NAME##_init,                   \
                                                std::size(NAME##_init) - 1);
#include "Opts.inc"
#undef PREFIX

static constexpr opt::OptTable::Info InfoTable[] = {
#define OPTION(PREFIX, NAME, ID, KIND, GROUP, ALIAS, ALIASARGS, FLAGS, PARAM,  \
               HELPTEXT, METAVAR, VALUES)                                      \
  {                                                                            \
      PREFIX,      NAME,      HELPTEXT,                                        \
      METAVAR,     OPT_##ID,  opt::Option::KIND##Class,                        \
      PARAM,       FLAGS,     OPT_##GROUP,                                     \
      OPT_##ALIAS, ALIASARGS, VALUES},
#include "Opts.inc"
#undef OPTION
};

class SymbolizerOptTable : public opt::GenericOptTable {
public:
  SymbolizerOptTable() : GenericOptTable(InfoTable) {
    setGroupedShortOptions(true);
  }
};
} // namespace

static std::string ToolName;

static void printError(const ErrorInfoBase &EI, StringRef Path) {
  WithColor::error(errs(), ToolName);
  if (!EI.isA<FileError>())
    errs() << "'" << Path << "': ";
  EI.log(errs());
  errs() << '\n';
}

template <typename T>
static void print(const Request &Request, Expected<T> &ResOrErr,
                  DIPrinter &Printer) {
  if (ResOrErr) {
    // No error, print the result.
    Printer.print(Request, *ResOrErr);
    return;
  }

  // Handle the error.
  bool PrintEmpty = true;
  handleAllErrors(std::move(ResOrErr.takeError()),
                  [&](const ErrorInfoBase &EI) {
                    PrintEmpty = Printer.printError(Request, EI);
                  });

  if (PrintEmpty)
    Printer.print(Request, T());
}

enum class OutputStyle { LLVM, GNU, JSON };

enum class Command {
  Code,
  Data,
  Frame,
};

static void enableDebuginfod(LLVMSymbolizer &Symbolizer,
                             const opt::ArgList &Args) {
  static bool IsEnabled = false;
  if (IsEnabled)
    return;
  IsEnabled = true;
  // Look up symbols using the debuginfod client.
  Symbolizer.setBuildIDFetcher(std::make_unique<DebuginfodFetcher>(
      Args.getAllArgValues(OPT_debug_file_directory_EQ)));
  // The HTTPClient must be initialized for use by the debuginfod client.
  HTTPClient::initialize();
}

static bool parseCommand(StringRef BinaryName, bool IsAddr2Line,
                         StringRef InputString, Command &Cmd,
                         std::string &ModuleName, object::BuildID &BuildID,
                         uint64_t &ModuleOffset) {
  const char kDelimiters[] = " \n\r";
  ModuleName = "";
  if (InputString.consume_front("CODE ")) {
    Cmd = Command::Code;
  } else if (InputString.consume_front("DATA ")) {
    Cmd = Command::Data;
  } else if (InputString.consume_front("FRAME ")) {
    Cmd = Command::Frame;
  } else {
    // If no cmd, assume it's CODE.
    Cmd = Command::Code;
  }

  const char *Pos;
  // Skip delimiters and parse input filename (if needed).
  if (BinaryName.empty() && BuildID.empty()) {
    bool HasFilePrefix = false;
    bool HasBuildIDPrefix = false;
    while (true) {
      if (InputString.consume_front("FILE:")) {
        if (HasFilePrefix)
          return false;
        HasFilePrefix = true;
        continue;
      }
      if (InputString.consume_front("BUILDID:")) {
        if (HasBuildIDPrefix)
          return false;
        HasBuildIDPrefix = true;
        continue;
      }
      break;
    }
    if (HasFilePrefix && HasBuildIDPrefix)
      return false;

    Pos = InputString.data();
    Pos += strspn(Pos, kDelimiters);
    if (*Pos == '"' || *Pos == '\'') {
      char Quote = *Pos;
      Pos++;
      const char *End = strchr(Pos, Quote);
      if (!End)
        return false;
      ModuleName = std::string(Pos, End - Pos);
      Pos = End + 1;
    } else {
      int NameLength = strcspn(Pos, kDelimiters);
      ModuleName = std::string(Pos, NameLength);
      Pos += NameLength;
    }
    if (HasBuildIDPrefix) {
      BuildID = parseBuildID(ModuleName);
      if (BuildID.empty())
        return false;
      ModuleName.clear();
    }
  } else {
    Pos = InputString.data();
    ModuleName = BinaryName.str();
  }
  // Skip delimiters and parse module offset.
  Pos += strspn(Pos, kDelimiters);
  int OffsetLength = strcspn(Pos, kDelimiters);
  StringRef Offset(Pos, OffsetLength);
  // GNU addr2line assumes the offset is hexadecimal and allows a redundant
  // "0x" or "0X" prefix; do the same for compatibility.
  if (IsAddr2Line)
    Offset.consume_front("0x") || Offset.consume_front("0X");
  return !Offset.getAsInteger(IsAddr2Line ? 16 : 0, ModuleOffset);
}

template <typename T>
void executeCommand(StringRef ModuleName, const T &ModuleSpec, Command Cmd,
                    uint64_t Offset, uint64_t AdjustVMA, bool ShouldInline,
                    OutputStyle Style, LLVMSymbolizer &Symbolizer,
                    DIPrinter &Printer) {
  uint64_t AdjustedOffset = Offset - AdjustVMA;
  object::SectionedAddress Address = {AdjustedOffset,
                                      object::SectionedAddress::UndefSection};
  Request SymRequest = {ModuleName, Offset};
  if (Cmd == Command::Data) {
    Expected<DIGlobal> ResOrErr = Symbolizer.symbolizeData(ModuleSpec, Address);
    print(SymRequest, ResOrErr, Printer);
  } else if (Cmd == Command::Frame) {
    Expected<std::vector<DILocal>> ResOrErr =
        Symbolizer.symbolizeFrame(ModuleSpec, Address);
    print(SymRequest, ResOrErr, Printer);
  } else if (ShouldInline) {
    Expected<DIInliningInfo> ResOrErr =
        Symbolizer.symbolizeInlinedCode(ModuleSpec, Address);
    print(SymRequest, ResOrErr, Printer);
  } else if (Style == OutputStyle::GNU) {
    // With PrintFunctions == FunctionNameKind::LinkageName (default)
    // and UseSymbolTable == true (also default), Symbolizer.symbolizeCode()
    // may override the name of an inlined function with the name of the topmost
    // caller function in the inlining chain. This contradicts the existing
    // behavior of addr2line. Symbolizer.symbolizeInlinedCode() overrides only
    // the topmost function, which suits our needs better.
    Expected<DIInliningInfo> ResOrErr =
        Symbolizer.symbolizeInlinedCode(ModuleSpec, Address);
    Expected<DILineInfo> Res0OrErr =
        !ResOrErr
            ? Expected<DILineInfo>(ResOrErr.takeError())
            : ((ResOrErr->getNumberOfFrames() == 0) ? DILineInfo()
                                                    : ResOrErr->getFrame(0));
    print(SymRequest, Res0OrErr, Printer);
  } else {
    Expected<DILineInfo> ResOrErr =
        Symbolizer.symbolizeCode(ModuleSpec, Address);
    print(SymRequest, ResOrErr, Printer);
  }
  Symbolizer.pruneCache();
}

static void symbolizeInput(const opt::InputArgList &Args,
                           object::BuildIDRef IncomingBuildID,
                           uint64_t AdjustVMA, bool IsAddr2Line,
                           OutputStyle Style, StringRef InputString,
                           LLVMSymbolizer &Symbolizer, DIPrinter &Printer) {
  Command Cmd;
  std::string ModuleName;
  object::BuildID BuildID(IncomingBuildID.begin(), IncomingBuildID.end());
  uint64_t Offset = 0;
  if (!parseCommand(Args.getLastArgValue(OPT_obj_EQ), IsAddr2Line,
                    StringRef(InputString), Cmd, ModuleName, BuildID, Offset)) {
    Printer.printInvalidCommand({ModuleName, std::nullopt}, InputString);
    return;
  }
  bool ShouldInline = Args.hasFlag(OPT_inlines, OPT_no_inlines, !IsAddr2Line);
  if (!BuildID.empty()) {
    assert(ModuleName.empty());
    if (!Args.hasArg(OPT_no_debuginfod))
      enableDebuginfod(Symbolizer, Args);
    std::string BuildIDStr = toHex(BuildID);
    executeCommand(BuildIDStr, BuildID, Cmd, Offset, AdjustVMA, ShouldInline,
                   Style, Symbolizer, Printer);
  } else {
    executeCommand(ModuleName, ModuleName, Cmd, Offset, AdjustVMA, ShouldInline,
                   Style, Symbolizer, Printer);
  }
}

static void printHelp(StringRef ToolName, const SymbolizerOptTable &Tbl,
                      raw_ostream &OS) {
  const char HelpText[] = " [options] addresses...";
  Tbl.printHelp(OS, (ToolName + HelpText).str().c_str(),
                ToolName.str().c_str());
  // TODO Replace this with OptTable API once it adds extrahelp support.
  OS << "\nPass @FILE as argument to read options from FILE.\n";
}

static opt::InputArgList parseOptions(int Argc, char *Argv[], bool IsAddr2Line,
                                      StringSaver &Saver,
                                      SymbolizerOptTable &Tbl) {
  StringRef ToolName = IsAddr2Line ? "llvm-addr2line" : "llvm-symbolizer";
  // The environment variable specifies initial options which can be overridden
  // by commnad line options.
  Tbl.setInitialOptionsFromEnvironment(IsAddr2Line ? "LLVM_ADDR2LINE_OPTS"
                                                   : "LLVM_SYMBOLIZER_OPTS");
  bool HasError = false;
  opt::InputArgList Args =
      Tbl.parseArgs(Argc, Argv, OPT_UNKNOWN, Saver, [&](StringRef Msg) {
        errs() << ("error: " + Msg + "\n");
        HasError = true;
      });
  if (HasError)
    exit(1);
  if (Args.hasArg(OPT_help)) {
    printHelp(ToolName, Tbl, outs());
    exit(0);
  }
  if (Args.hasArg(OPT_version)) {
    outs() << ToolName << '\n';
    cl::PrintVersionMessage();
    exit(0);
  }

  return Args;
}

template <typename T>
static void parseIntArg(const opt::InputArgList &Args, int ID, T &Value) {
  if (const opt::Arg *A = Args.getLastArg(ID)) {
    StringRef V(A->getValue());
    if (!llvm::to_integer(V, Value, 0)) {
      errs() << A->getSpelling() +
                    ": expected a non-negative integer, but got '" + V + "'";
      exit(1);
    }
  } else {
    Value = 0;
  }
}

static FunctionNameKind decideHowToPrintFunctions(const opt::InputArgList &Args,
                                                  bool IsAddr2Line) {
  if (Args.hasArg(OPT_functions))
    return FunctionNameKind::LinkageName;
  if (const opt::Arg *A = Args.getLastArg(OPT_functions_EQ))
    return StringSwitch<FunctionNameKind>(A->getValue())
        .Case("none", FunctionNameKind::None)
        .Case("short", FunctionNameKind::ShortName)
        .Default(FunctionNameKind::LinkageName);
  return IsAddr2Line ? FunctionNameKind::None : FunctionNameKind::LinkageName;
}

static std::optional<bool> parseColorArg(const opt::InputArgList &Args) {
  if (Args.hasArg(OPT_color))
    return true;
  if (const opt::Arg *A = Args.getLastArg(OPT_color_EQ))
    return StringSwitch<std::optional<bool>>(A->getValue())
        .Case("always", true)
        .Case("never", false)
        .Case("auto", std::nullopt);
  return std::nullopt;
}

static object::BuildID parseBuildIDArg(const opt::InputArgList &Args, int ID) {
  const opt::Arg *A = Args.getLastArg(ID);
  if (!A)
    return {};

  StringRef V(A->getValue());
  object::BuildID BuildID = parseBuildID(V);
  if (BuildID.empty()) {
    errs() << A->getSpelling() + ": expected a build ID, but got '" + V + "'\n";
    exit(1);
  }
  return BuildID;
}

// Symbolize markup from stdin and write the result to stdout.
static void filterMarkup(const opt::InputArgList &Args, LLVMSymbolizer &Symbolizer) {
  MarkupFilter Filter(outs(), Symbolizer, parseColorArg(Args));
  std::string InputString;
  while (std::getline(std::cin, InputString)) {
    InputString += '\n';
    Filter.filter(InputString);
  }
  Filter.finish();
}

ExitOnError ExitOnErr;

int main(int argc, char **argv) {
  InitLLVM X(argc, argv);
  sys::InitializeCOMRAII COM(sys::COMThreadingMode::MultiThreaded);

  ToolName = argv[0];
  bool IsAddr2Line = sys::path::stem(ToolName).contains("addr2line");
  BumpPtrAllocator A;
  StringSaver Saver(A);
  SymbolizerOptTable Tbl;
  opt::InputArgList Args = parseOptions(argc, argv, IsAddr2Line, Saver, Tbl);

  LLVMSymbolizer::Options Opts;
  uint64_t AdjustVMA;
  PrinterConfig Config;
  parseIntArg(Args, OPT_adjust_vma_EQ, AdjustVMA);
  if (const opt::Arg *A = Args.getLastArg(OPT_basenames, OPT_relativenames)) {
    Opts.PathStyle =
        A->getOption().matches(OPT_basenames)
            ? DILineInfoSpecifier::FileLineInfoKind::BaseNameOnly
            : DILineInfoSpecifier::FileLineInfoKind::RelativeFilePath;
  } else {
    Opts.PathStyle = DILineInfoSpecifier::FileLineInfoKind::AbsoluteFilePath;
  }
  Opts.DebugFileDirectory = Args.getAllArgValues(OPT_debug_file_directory_EQ);
  Opts.DefaultArch = Args.getLastArgValue(OPT_default_arch_EQ).str();
  Opts.Demangle = Args.hasFlag(OPT_demangle, OPT_no_demangle, !IsAddr2Line);
  Opts.DWPName = Args.getLastArgValue(OPT_dwp_EQ).str();
  Opts.FallbackDebugPath =
      Args.getLastArgValue(OPT_fallback_debug_path_EQ).str();
  Opts.PrintFunctions = decideHowToPrintFunctions(Args, IsAddr2Line);
  parseIntArg(Args, OPT_print_source_context_lines_EQ,
              Config.SourceContextLines);
  Opts.RelativeAddresses = Args.hasArg(OPT_relative_address);
  Opts.UntagAddresses =
      Args.hasFlag(OPT_untag_addresses, OPT_no_untag_addresses, !IsAddr2Line);
  Opts.UseDIA = Args.hasArg(OPT_use_dia);
#if !defined(LLVM_ENABLE_DIA_SDK)
  if (Opts.UseDIA) {
    WithColor::warning() << "DIA not available; using native PDB reader\n";
    Opts.UseDIA = false;
  }
#endif
  Opts.UseSymbolTable = true;
  if (Args.hasArg(OPT_cache_size_EQ))
    parseIntArg(Args, OPT_cache_size_EQ, Opts.MaxCacheSize);
  Config.PrintAddress = Args.hasArg(OPT_addresses);
  Config.PrintFunctions = Opts.PrintFunctions != FunctionNameKind::None;
  Config.Pretty = Args.hasArg(OPT_pretty_print);
  Config.Verbose = Args.hasArg(OPT_verbose);

  for (const opt::Arg *A : Args.filtered(OPT_dsym_hint_EQ)) {
    StringRef Hint(A->getValue());
    if (sys::path::extension(Hint) == ".dSYM") {
      Opts.DsymHints.emplace_back(Hint);
    } else {
      errs() << "Warning: invalid dSYM hint: \"" << Hint
             << "\" (must have the '.dSYM' extension).\n";
    }
  }

  LLVMSymbolizer Symbolizer(Opts);

  if (Args.hasFlag(OPT_debuginfod, OPT_no_debuginfod, canUseDebuginfod()))
    enableDebuginfod(Symbolizer, Args);

  if (Args.hasArg(OPT_filter_markup)) {
    filterMarkup(Args, Symbolizer);
    return 0;
  }

  auto Style = IsAddr2Line ? OutputStyle::GNU : OutputStyle::LLVM;
  if (const opt::Arg *A = Args.getLastArg(OPT_output_style_EQ)) {
    if (strcmp(A->getValue(), "GNU") == 0)
      Style = OutputStyle::GNU;
    else if (strcmp(A->getValue(), "JSON") == 0)
      Style = OutputStyle::JSON;
    else
      Style = OutputStyle::LLVM;
  }

  if (Args.hasArg(OPT_build_id_EQ) && Args.hasArg(OPT_obj_EQ)) {
    errs() << "error: cannot specify both --build-id and --obj\n";
    return EXIT_FAILURE;
  }
  object::BuildID BuildID = parseBuildIDArg(Args, OPT_build_id_EQ);

  std::unique_ptr<DIPrinter> Printer;
  if (Style == OutputStyle::GNU)
    Printer = std::make_unique<GNUPrinter>(outs(), printError, Config);
  else if (Style == OutputStyle::JSON)
    Printer = std::make_unique<JSONPrinter>(outs(), Config);
  else
    Printer = std::make_unique<LLVMPrinter>(outs(), printError, Config);

  // When an input file is specified, exit immediately if the file cannot be
  // read. If getOrCreateModuleInfo succeeds, symbolizeInput will reuse the
  // cached file handle.
  if (auto *Arg = Args.getLastArg(OPT_obj_EQ); Arg) {
    auto Status = Symbolizer.getOrCreateModuleInfo(Arg->getValue());
    if (!Status) {
      Request SymRequest = {Arg->getValue(), 0};
      handleAllErrors(Status.takeError(), [&](const ErrorInfoBase &EI) {
        Printer->printError(SymRequest, EI);
      });
      return EXIT_FAILURE;
    }
  }

  std::vector<std::string> InputAddresses = Args.getAllArgValues(OPT_INPUT);
  if (InputAddresses.empty()) {
    const int kMaxInputStringLength = 1024;
    char InputString[kMaxInputStringLength];

    while (fgets(InputString, sizeof(InputString), stdin)) {
      // Strip newline characters.
      std::string StrippedInputString(InputString);
      llvm::erase_if(StrippedInputString,
                     [](char c) { return c == '\r' || c == '\n'; });
      symbolizeInput(Args, BuildID, AdjustVMA, IsAddr2Line, Style,
                     StrippedInputString, Symbolizer, *Printer);
      outs().flush();
    }
  } else {
    Printer->listBegin();
    for (StringRef Address : InputAddresses)
      symbolizeInput(Args, BuildID, AdjustVMA, IsAddr2Line, Style, Address,
                     Symbolizer, *Printer);
    Printer->listEnd();
  }

  return 0;
}
