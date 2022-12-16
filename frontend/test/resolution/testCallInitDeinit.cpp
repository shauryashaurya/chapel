/*
 * Copyright 2021-2023 Hewlett Packard Enterprise Development LP
 * Other additional copyright holders may be indicated within.
 *
 * The entirety of this work is licensed under the Apache License,
 * Version 2.0 (the "License"); you may not use this file except
 * in compliance with the License.
 *
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "test-resolution.h"

#include "chpl/parsing/parsing-queries.h"
#include "chpl/resolution/resolution-queries.h"
#include "chpl/resolution/scope-queries.h"
#include "chpl/resolution/split-init.h"
#include "chpl/uast/Call.h"
#include "chpl/uast/Comment.h"
#include "chpl/uast/Identifier.h"
#include "chpl/uast/Module.h"
#include "chpl/uast/Variable.h"

#include "./ErrorGuard.h"

using ActionElt = std::tuple<AssociatedAction::Action,
                             std::string, /* ID where action occurs */
                             std::string /* ID acted upon or "" */ >;
using Actions = std::vector<ActionElt>;

static std::string idToStr(Context* context, ID id) {
  std::string name = id.str();
  if (const AstNode* ast = idToAst(context, id)) {
    if (auto nd = ast->toNamedDecl()) {
      name = nd->name().str();
    }
  }

  return name;
}

static void gatherActions(Context* context,
                          const AstNode* ast,
                          const ResolvedFunction* r,
                          Actions& actions) {

  // gather actions for child nodes
  for (auto child : ast->children()) {
    gatherActions(context, child, r, actions);
  }

  // gather actions for this node
  const ResolvedExpression* re = r->resolutionById().byAstOrNull(ast);
  if (re != nullptr) {
    for (auto act: re->associatedActions()) {
      if (act.action() == AssociatedAction::DEINIT) {
        actions.push_back(std::make_tuple(act.action(),
                                          idToStr(context, ast->id()),
                                          idToStr(context, act.id())));
      } else {
        // ignore acted-upon ID expect for DEINIT
        actions.push_back(std::make_tuple(act.action(),
                                          idToStr(context, ast->id()),
                                          ""));
      }
    }
  }
}


static void printAction(const ActionElt& a) {
  AssociatedAction::Action gotAction;
  std::string gotInId;
  std::string gotActId;

  gotAction = std::get<0>(a);
  gotInId = std::get<1>(a);
  gotActId = std::get<2>(a);

  printf("  %s in %s",
         AssociatedAction::kindToString(gotAction),
         gotInId.c_str());

  if (!gotActId.empty()) {
    printf(" for id %s", gotActId.c_str());
  }
  printf("\n");
}

static void printActions(const Actions& actions) {
  for (auto act : actions) {
    printAction(act);
  }
}

// resolves the last function
// checks that the actions match the passed ones
static void testActions(const char* test,
                        const char* program,
                        Actions expected,
                        bool expectErrors=false) {
  printf("### %s\n\n", test);

  Context ctx;
  Context* context = &ctx;
  ErrorGuard guard(context);

  std::string testname = test;
  testname += ".chpl";
  auto path = UniqueString::get(context, testname);
  std::string contents = program;
  setFileText(context, path, contents);

  const ModuleVec& vec = parseToplevel(context, path);
  assert(vec.size() == 1);
  const Module* M = vec[0]->toModule();
  assert(M);
  assert(M->numStmts() >= 1);

  const Function* func = M->stmt(M->numStmts()-1)->toFunction();
  assert(func);

  printf("uAST:\n");
  func->dump();

  // resolve runM1
  const ResolvedFunction* r = resolveConcreteFunction(context, func->id());
  assert(r);

  Actions actions;
  gatherActions(context, func, r, actions);

  printf("Expecting:\n");
  printActions(expected);
  printf("Got:\n");
  printActions(actions);
  printf("\n");

  size_t i = 0;
  size_t j = 0;
  while (i < actions.size() && j < expected.size()) {
    AssociatedAction::Action gotAction, expectAction;
    std::string gotInId, expectInId;
    std::string gotActId, expectActId;

    gotAction = std::get<0>(actions[i]);
    gotInId = std::get<1>(actions[i]);
    gotActId = std::get<2>(actions[i]);

    expectAction = std::get<0>(expected[i]);
    expectInId = std::get<1>(expected[i]);
    expectActId = std::get<2>(expected[i]);

    if (gotAction != expectAction) {
      assert(false && "Failure: mismatched action type");
    }

    if (gotInId != expectInId) {
      assert(false && "Failure: mismatched containing ID");
    }
    if (gotActId != expectActId) {
      assert(false && "Failure: mismatched acted upon ID");
    }

    i++;
    j++;
  }

  if (i < actions.size()) {
    assert(false && "Failure: extra action");
  }

  if (j < expected.size()) {
    assert(false && "Failure: expected action is missing");
  }

  size_t errCount = guard.realizeErrors();
  if (expectErrors) {
    assert(errCount > 0);
  } else {
    assert(errCount == 0);
  }
}

// test very basic default init & deinit
static void test1() {
  testActions("test1",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.deinit() { }
        proc test() {
          var x:R;
        }
      }
    )"""",
    {
      {AssociatedAction::DEFAULT_INIT, "x",        ""},
      {AssociatedAction::DEINIT,       "M.test@2", "x"}
    });
}

// test deinit order when split initing & move from value call
static void test2a() {
  testActions("test2a",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R;
          var y:R;
          y = makeR();
          x = makeR();
        }
      }
    )"""",
    {
      {AssociatedAction::DEINIT, "M.test@12", "x"},
      {AssociatedAction::DEINIT, "M.test@12", "y"}
    });
}

// test deinit order when split initing
static void test2b() {
  testActions("test2b",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R;
          var y:R;
          x = makeR();
          y = makeR();
        }
      }
    )"""",
    {
      {AssociatedAction::DEINIT, "M.test@12", "y"},
      {AssociatedAction::DEINIT, "M.test@12", "x"}
    });
}

// test deinit order when split initing
static void test2c() {
  testActions("test2c",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R;
          var y:R;
          {
            x = makeR();
            y = makeR();
          }
        }
      }
    )"""",
    {
      {AssociatedAction::DEINIT, "M.test@13", "y"},
      {AssociatedAction::DEINIT, "M.test@13", "x"}
    });
}

// test assignment between values
// this one has no split init and no copy elision
static void test3a() {
  testActions("test3a",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        operator R.=(ref lhs: R, rhs: R) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R;
          var y:R;
          x; // no split init
          x = y; // assignment -- not a copy so no elision
        }
      }
    )"""",
    {
      {AssociatedAction::DEFAULT_INIT, "x",        ""},
      {AssociatedAction::DEFAULT_INIT, "y",        ""},
      {AssociatedAction::ASSIGN,       "M.test@7", ""},
      {AssociatedAction::DEINIT,       "M.test@8", "y"},
      {AssociatedAction::DEINIT,       "M.test@8", "x"}
    });
}

static void test3b() {
  testActions("test3b",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        operator R.=(ref lhs: R, rhs: R) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R;
          var y:R;
          x = y; // split init
          y; // no copy elision
        }
      }
    )"""",
    {
      {AssociatedAction::DEFAULT_INIT, "y",        ""},
      {AssociatedAction::COPY_INIT,    "M.test@6", ""},
      {AssociatedAction::DEINIT,       "M.test@8", "x"},
      {AssociatedAction::DEINIT,       "M.test@8", "y"}
    });
}

static void test3c() {
  testActions("test3c",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        operator R.=(ref lhs: R, rhs: R) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R;
          var y:R;
          x = y; // split init + copy elision
        }
      }
    )"""",
    {
      {AssociatedAction::DEFAULT_INIT, "y",        ""},
      {AssociatedAction::DEINIT,       "M.test@7", "x"}
    });
}

static void test3d() {
  testActions("test3d",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        operator R.=(ref lhs: R, rhs: R) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R;
          var y:R;
          {
            x = y; // split init + copy elision
          }
        }
      }
    )"""",
    {
      {AssociatedAction::DEFAULT_INIT, "y",        ""},
      {AssociatedAction::DEINIT,       "M.test@8", "x"}
    });
}

// test copy-initialization from variable decl with init
static void test4a() {
  testActions("test4a",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        operator R.=(ref lhs: R, rhs: R) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R = makeR();
        }
      }
    )"""",
    {
      {AssociatedAction::DEINIT,       "M.test@4", "x"}
    });
}

static void test4b() {
  testActions("test4b",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        operator R.=(ref lhs: R, rhs: R) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R = makeR();
          var y:R = x;
          x; // prevent copy elision
        }
      }
    )"""",
    {
      {AssociatedAction::COPY_INIT,    "y",        ""},
      {AssociatedAction::DEINIT,       "M.test@8", "y"},
      {AssociatedAction::DEINIT,       "M.test@8", "x"}
    });
}

static void test4c() {
  testActions("test4c",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        operator R.=(ref lhs: R, rhs: R) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R = makeR();
          var y:R = x; // copy is elided
        }
      }
    )"""",
    {
      {AssociatedAction::DEINIT,       "M.test@7", "y"}
    });
}

// test cross-type variable init from an integer
static void test5a() {
  testActions("test5a",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: int) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R = 4;
        }
      }
    )"""",
    {
      {AssociatedAction::INIT_OTHER,   "x",        ""},
      {AssociatedAction::DEINIT,       "M.test@3", "x"}
    });
}

static void test5b() {
  testActions("test5b",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: int) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var x:R;
          x = 4; // split init
        }
      }
    )"""",
    {
      {AssociatedAction::INIT_OTHER,   "M.test@4", ""},
      {AssociatedAction::DEINIT,       "M.test@5", "x"},
    });
}

static void test5c() {
  testActions("test5c",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: int) { }
        proc R.deinit() { }
        proc makeR() {
          return new R();
        }
        proc test() {
          var i = 4;
          var x:R = i;
        }
      }
    )"""",
    {
      {AssociatedAction::INIT_OTHER,   "x",        ""},
      {AssociatedAction::DEINIT,       "M.test@5", "x"},
    });
}


// test cross-type variable init from another record
static void test6a() {
  testActions("test6a",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        proc R.init=(other: U) { }
        proc R.deinit() { }
        record U { }
        proc U.init() { }
        proc U.init=(other: U) { }
        proc U.deinit() { }

        proc makeU() {
          return new U();
        }
        proc test() {
          var x:R = makeU();
        }
      }
    )"""",
    {
      {AssociatedAction::INIT_OTHER,   "x",        ""},
      {AssociatedAction::DEINIT,       "M.test@4", "M.test@2"},
      {AssociatedAction::DEINIT,       "M.test@4", "x"}
    });
}

static void test6b() {
  testActions("test6b",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        proc R.init=(other: U) { }
        proc R.deinit() { }
        record U { }
        proc U.init() { }
        proc U.init=(other: U) { }
        proc U.deinit() { }

        proc makeU() {
          return new U();
        }
        proc test() {
          var x:R;
          var y:U;
          x = y;
        }
      }
    )"""",
    {
      {AssociatedAction::DEFAULT_INIT, "y",        ""},
      {AssociatedAction::INIT_OTHER,   "M.test@6", ""},
      {AssociatedAction::DEINIT,       "M.test@7", "x"},
      {AssociatedAction::DEINIT,       "M.test@7", "y"}
    });
}

static void test6c() {
  testActions("test6c",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        proc R.init=(other: U) { }
        proc R.deinit() { }
        record U { }
        proc U.init() { }
        proc U.init=(other: U) { }
        proc U.deinit() { }

        proc makeU() {
          return new U();
        }
        proc test() {
          var x:R;
          x = makeU();
        }
      }
    )"""",
    {
      {AssociatedAction::INIT_OTHER,   "M.test@5", ""},
      {AssociatedAction::DEINIT,       "M.test@5", "M.test@4"},
      {AssociatedAction::DEINIT,       "M.test@6", "x"}
    });
}



// testing cross-type init= with 'in' intent
static void test7a() {
  testActions("test7a",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        proc R.init=(in other: U) { }
        proc R.deinit() { }
        record U { }
        proc U.init() { }
        proc U.init=(other: U) { }
        proc U.deinit() { }

        proc makeU() {
          return new U();
        }
        proc test() {
          var x:R = makeU();
        }
      }
    )"""",
    {
      {AssociatedAction::INIT_OTHER,   "x",        ""},
      {AssociatedAction::DEINIT,       "M.test@4", "x"}
    });
}

static void test7b() {
  testActions("test7b",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        proc R.init=(in other: U) { }
        proc R.deinit() { }
        record U { }
        proc U.init() { }
        proc U.init=(other: U) { }
        proc U.deinit() { }

        proc makeU() {
          return new U();
        }
        proc test() {
          var y:U;
          var x:R = y; // the copy to 'init=(in)' is elided
        }
      }
    )"""",
    {
      {AssociatedAction::DEFAULT_INIT, "y",        ""},
      {AssociatedAction::INIT_OTHER,   "x",        ""},
      {AssociatedAction::DEINIT,       "M.test@5", "x"},
    });
}

static void test7c() {
  testActions("test7c",
    R""""(
      module M {
        record R { }
        proc R.init() { }
        proc R.init=(other: R) { }
        proc R.init=(in other: U) { }
        proc R.deinit() { }
        record U { }
        proc U.init() { }
        proc U.init=(other: U) { }
        proc U.deinit() { }

        proc makeU() {
          return new U();
        }
        proc test() {
          var y:U;
          var x:R = y;
          y;
        }
      }
    )"""",
    {
      {AssociatedAction::DEFAULT_INIT, "y",        ""},
      {AssociatedAction::COPY_INIT,    "x",        ""},
      {AssociatedAction::INIT_OTHER,   "x",        ""},
      {AssociatedAction::DEINIT,       "M.test@6", "M.test@3"},
      {AssociatedAction::DEINIT,       "M.test@6", "x"},
      {AssociatedAction::DEINIT,       "M.test@6", "y"}
    });
}


int main() {
  test1();

  test2a();
  test2b();
  test2c();

  test3a();
  test3b();
  test3c();
  test3d();

  test4a();
  test4b();
  test4c();

  test5a();
  test5b();
  test5c();

  test6a();
  test6b();
  test6c();

  test7a();
  test7b();
  test7c();

  return 0;
}
