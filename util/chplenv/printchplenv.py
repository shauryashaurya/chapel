#!/usr/bin/env python3

"""Usage: printchplenv [options]

Print the current Chapel configuration. Arguments allow selection of
what gets printed [content], how it gets printed [format], and what gets
filtered [filter].

The default [content] provides user-facing variables.

Options:
  -h, --help    Show this help message and exit

  [shortcut]
  --all         Shortcut for --compiler --runtime --launcher, includes defaults

  [content]
  --compiler    Select variables describing the configuration of the compiler
  --runtime     Select variables describing the configuration of the runtime
  --launcher    Select variables describing the configuration of the launcher
  --internal    Select additional variables used during builds
                 this flag is incompatible with [format]: --path

  [filter]
  --[no-]tidy   (default) [don't] Omit sub-variables irrelevant to the current
                 configuration
  --anonymize   Omit machine specific details, script location, and CHPL_HOME
  --overrides   Omit variables that have not been user supplied via environment
                 or chplconfig

  [format]
  --pretty      (default) Print variables in format: CHPL_KEY: VALUE
                 indicating which options are set by environment variables (*)
                 and which are set by configuration files (+)
  --simple      Print variables in format: CHPL_KEY=VALUE
                 output is compatible with chplconfig format
  --make        Print variables in format: CHPL_MAKE_KEY=VALUE
  --path        Print variables in format: VALUE1/VALUE2/...
                 this flag always excludes CHPL_HOME and CHPL_MAKE
"""

from collections import namedtuple
from functools import partial
import optparse
import os
from sys import stdout, path

from chplenv import *

ChapelEnv = namedtuple('ChapelEnv', ['name', 'content', 'shortname'])

# Set default argument of 'shortname' to None
ChapelEnv.__new__.__defaults__ = (None,)

# Define base sets
COMPILER = set(['compiler'])
LAUNCHER = set(['launcher'])
RUNTIME = set(['runtime'])
INTERNAL = set(['internal'])
NOPATH = set(['nopath'])     # for variables to be skipped for --path
DEFAULT = set(['default'])

# Global ordered list that stores names, content-categories, and shortnames
CHPL_ENVS = [
    ChapelEnv('CHPL_HOST_PLATFORM', COMPILER | LAUNCHER),
    ChapelEnv('CHPL_HOST_COMPILER', COMPILER | LAUNCHER),
    ChapelEnv('  CHPL_HOST_CC', COMPILER | NOPATH),
    ChapelEnv('  CHPL_HOST_CXX', COMPILER | NOPATH),
    ChapelEnv('  CHPL_HOST_BUNDLED_COMPILE_ARGS', INTERNAL),
    ChapelEnv('  CHPL_HOST_SYSTEM_COMPILE_ARGS', INTERNAL),
    ChapelEnv('  CHPL_HOST_BUNDLED_LINK_ARGS', INTERNAL),
    ChapelEnv('  CHPL_HOST_SYSTEM_LINK_ARGS', INTERNAL),
    ChapelEnv('CHPL_HOST_ARCH', COMPILER | LAUNCHER),
    ChapelEnv('CHPL_HOST_CPU', INTERNAL),
    ChapelEnv('CHPL_TARGET_PLATFORM', RUNTIME | DEFAULT),
    ChapelEnv('CHPL_TARGET_COMPILER', RUNTIME | DEFAULT),
    ChapelEnv('  CHPL_TARGET_CC', RUNTIME | NOPATH),
    ChapelEnv('  CHPL_TARGET_CXX', RUNTIME | NOPATH),
    ChapelEnv('  CHPL_TARGET_COMPILER_PRGENV', INTERNAL),
    ChapelEnv('  CHPL_TARGET_BUNDLED_COMPILE_ARGS', INTERNAL),
    ChapelEnv('  CHPL_TARGET_SYSTEM_COMPILE_ARGS', INTERNAL),
    ChapelEnv('  CHPL_TARGET_BUNDLED_LINK_ARGS', INTERNAL),
    ChapelEnv('  CHPL_TARGET_SYSTEM_LINK_ARGS', INTERNAL),
    ChapelEnv('CHPL_TARGET_ARCH', RUNTIME | DEFAULT),
    ChapelEnv('CHPL_TARGET_CPU', RUNTIME | DEFAULT, 'cpu'),
    ChapelEnv('CHPL_RUNTIME_CPU', INTERNAL),
    ChapelEnv('CHPL_TARGET_CPU_FLAG', INTERNAL),
    ChapelEnv('CHPL_TARGET_BACKEND_CPU', INTERNAL),
    ChapelEnv('CHPL_LOCALE_MODEL', RUNTIME | LAUNCHER | DEFAULT, 'loc'),
    ChapelEnv('  CHPL_GPU_CODEGEN', RUNTIME | NOPATH),
    ChapelEnv('  CHPL_CUDA_PATH', RUNTIME | NOPATH),
    ChapelEnv('CHPL_COMM', RUNTIME | LAUNCHER | DEFAULT, 'comm'),
    ChapelEnv('  CHPL_COMM_SUBSTRATE', RUNTIME | LAUNCHER | DEFAULT),
    ChapelEnv('  CHPL_GASNET_SEGMENT', RUNTIME | LAUNCHER | DEFAULT),
    ChapelEnv('  CHPL_LIBFABRIC', RUNTIME | INTERNAL | DEFAULT),
    ChapelEnv('CHPL_TASKS', RUNTIME | LAUNCHER | DEFAULT, 'tasks'),
    ChapelEnv('CHPL_LAUNCHER', LAUNCHER | DEFAULT, 'launch'),
    ChapelEnv('CHPL_TIMERS', RUNTIME | LAUNCHER | DEFAULT, 'tmr'),
    ChapelEnv('CHPL_UNWIND', RUNTIME | LAUNCHER | DEFAULT, 'unwind'),
    ChapelEnv('CHPL_HOST_MEM', COMPILER, 'hostmem'),
    ChapelEnv('  CHPL_HOST_JEMALLOC', INTERNAL, 'jemalloc'),
    ChapelEnv('CHPL_MEM', RUNTIME | LAUNCHER | DEFAULT, 'mem'),
    ChapelEnv('CHPL_TARGET_MEM', INTERNAL, 'mem'),
    ChapelEnv('  CHPL_TARGET_JEMALLOC', INTERNAL, 'jemalloc'),
    ChapelEnv('CHPL_MAKE', INTERNAL, 'make'),
    ChapelEnv('CHPL_ATOMICS', RUNTIME | LAUNCHER | DEFAULT, 'atomics'),
    ChapelEnv('  CHPL_NETWORK_ATOMICS', INTERNAL | DEFAULT),
    ChapelEnv('CHPL_GMP', INTERNAL | DEFAULT, 'gmp'),
    ChapelEnv('  CHPL_GMP_IS_OVERRIDDEN', INTERNAL),
    ChapelEnv('CHPL_HWLOC', RUNTIME | DEFAULT, 'hwloc'),
    ChapelEnv('CHPL_RE2', RUNTIME | DEFAULT, 're2'),
    ChapelEnv('  CHPL_RE2_IS_OVERRIDDEN', INTERNAL),
    ChapelEnv('CHPL_LLVM', COMPILER | DEFAULT, 'llvm'),
    ChapelEnv('  CHPL_LLVM_CONFIG', COMPILER | NOPATH),
    ChapelEnv('  CHPL_LLVM_CLANG_C', INTERNAL),
    ChapelEnv('  CHPL_LLVM_CLANG_CXX', INTERNAL),
    ChapelEnv('CHPL_AUX_FILESYS', RUNTIME | DEFAULT, 'fs'),
    ChapelEnv('CHPL_LIB_PIC', RUNTIME | LAUNCHER, 'lib_pic'),
    ChapelEnv('CHPL_SANITIZE', COMPILER | LAUNCHER, 'san'),
    ChapelEnv('CHPL_SANITIZE_EXE', RUNTIME, 'san'),
    ChapelEnv('CHPL_RUNTIME_SUBDIR', INTERNAL),
    ChapelEnv('CHPL_LAUNCHER_SUBDIR', INTERNAL),
    ChapelEnv('CHPL_COMPILER_SUBDIR', INTERNAL),
    ChapelEnv('CHPL_HOST_BIN_SUBDIR', INTERNAL),
    ChapelEnv('CHPL_TARGET_BIN_SUBDIR', INTERNAL),
    ChapelEnv('CHPL_SYS_MODULES_SUBDIR', INTERNAL),
    ChapelEnv('  CHPL_LLVM_UNIQ_CFG_PATH', INTERNAL),
    ChapelEnv('  CHPL_GASNET_UNIQ_CFG_PATH', INTERNAL),
    ChapelEnv('  CHPL_GMP_UNIQ_CFG_PATH', INTERNAL),
    ChapelEnv('  CHPL_HWLOC_UNIQ_CFG_PATH', INTERNAL),
    ChapelEnv('  CHPL_JEMALLOC_UNIQ_CFG_PATH',INTERNAL),
    ChapelEnv('  CHPL_LIBFABRIC_UNIQ_CFG_PATH', INTERNAL),
    ChapelEnv('  CHPL_LIBUNWIND_UNIQ_CFG_PATH', INTERNAL),
    ChapelEnv('  CHPL_QTHREAD_UNIQ_CFG_PATH', INTERNAL),
    ChapelEnv('  CHPL_RE2_UNIQ_CFG_PATH', INTERNAL),
    ChapelEnv('  CHPL_PE_CHPL_PKGCONFIG_LIBS', INTERNAL),
]

# Global map of environment variable names to values
ENV_VALS = {}

"""Compute '--all' env var values and populate global dict, ENV_VALS"""
def compute_all_values():
    global ENV_VALS

    ENV_VALS['CHPL_HOME'] = chpl_home_utils.get_chpl_home()
    ENV_VALS['CHPL_HOST_PLATFORM'] = chpl_platform.get('host')

    host_compiler = chpl_compiler.get('host')
    host_compiler_c = chpl_compiler.get_compiler_command('host', 'c')
    host_compiler_cpp = chpl_compiler.get_compiler_command('host', 'c++')
    ENV_VALS['CHPL_HOST_COMPILER'] = host_compiler
    ENV_VALS['  CHPL_HOST_CC'] = " ".join(host_compiler_c)
    ENV_VALS['  CHPL_HOST_CXX'] = " ".join(host_compiler_cpp)
    ENV_VALS['CHPL_HOST_ARCH'] = chpl_arch.get('host')
    ENV_VALS['CHPL_HOST_CPU'] = chpl_cpu.get('host').cpu
    ENV_VALS['CHPL_TARGET_PLATFORM'] = chpl_platform.get('target')

    target_compiler = chpl_compiler.get('target')
    target_compiler_c = chpl_compiler.get_compiler_command('target', 'c')
    target_compiler_cpp = chpl_compiler.get_compiler_command('target', 'c++')
    target_compiler_prgenv = chpl_compiler.get_prgenv_compiler()
    ENV_VALS['CHPL_TARGET_COMPILER'] = target_compiler
    ENV_VALS['  CHPL_TARGET_CC'] = " ".join(target_compiler_c)
    ENV_VALS['  CHPL_TARGET_CXX'] = " ".join(target_compiler_cpp)
    ENV_VALS['  CHPL_TARGET_COMPILER_PRGENV'] = target_compiler_prgenv

    ENV_VALS['CHPL_TARGET_ARCH'] = chpl_arch.get('target')
    ENV_VALS['CHPL_TARGET_CPU'] = chpl_cpu.get('target').cpu

    # Use module's LCD architecture in case it was built before
    # Internal, but this value is used in place of CHPL_TARGET_CPU for --path
    ENV_VALS['CHPL_RUNTIME_CPU'] = chpl_cpu.get('target',
            get_lcd=chpl_home_utils.using_chapel_module()).cpu

    ENV_VALS['CHPL_LOCALE_MODEL'] = chpl_locale_model.get()
    ENV_VALS['  CHPL_GPU_CODEGEN'] = chpl_gpu.get()
    ENV_VALS['  CHPL_CUDA_PATH'] = chpl_gpu.get_cuda_path()
    ENV_VALS['CHPL_COMM'] = chpl_comm.get()
    ENV_VALS['  CHPL_COMM_SUBSTRATE'] = chpl_comm_substrate.get()
    ENV_VALS['  CHPL_GASNET_SEGMENT'] = chpl_comm_segment.get()
    ENV_VALS['  CHPL_LIBFABRIC'] = chpl_libfabric.get()
    ENV_VALS['CHPL_TASKS'] = chpl_tasks.get()
    ENV_VALS['CHPL_LAUNCHER'] = chpl_launcher.get()
    ENV_VALS['CHPL_TIMERS'] = chpl_timers.get()
    ENV_VALS['CHPL_UNWIND'] = chpl_unwind.get()
    ENV_VALS['CHPL_HOST_MEM'] = chpl_mem.get('host')
    ENV_VALS['CHPL_MEM'] = chpl_mem.get('target')
    ENV_VALS['  CHPL_HOST_JEMALLOC'] = chpl_jemalloc.get('host')
    ENV_VALS['  CHPL_TARGET_JEMALLOC'] = chpl_jemalloc.get('target')
    ENV_VALS['CHPL_MAKE'] = chpl_make.get()
    ENV_VALS['CHPL_ATOMICS'] = chpl_atomics.get()
    ENV_VALS['  CHPL_NETWORK_ATOMICS'] = chpl_atomics.get('network')
    ENV_VALS['CHPL_GMP'] = chpl_gmp.get()
    ENV_VALS['  CHPL_GMP_IS_OVERRIDDEN'] = chpl_gmp.is_overridden()
    ENV_VALS['CHPL_HWLOC'] = chpl_hwloc.get()
    ENV_VALS['CHPL_RE2'] = chpl_re2.get()
    ENV_VALS['  CHPL_RE2_IS_OVERRIDDEN'] = chpl_re2.is_overridden()
    ENV_VALS['CHPL_LLVM'] = chpl_llvm.get()
    ENV_VALS['  CHPL_LLVM_CONFIG'] = chpl_llvm.get_llvm_config()
    llvm_clang_c = chpl_llvm.get_llvm_clang('c')
    llvm_clang_cxx = chpl_llvm.get_llvm_clang('c++')
    ENV_VALS['  CHPL_LLVM_CLANG_C'] = " ".join(llvm_clang_c)
    ENV_VALS['  CHPL_LLVM_CLANG_CXX'] = " ".join(llvm_clang_cxx)
    aux_filesys = chpl_aux_filesys.get()
    ENV_VALS['CHPL_AUX_FILESYS'] = '_'.join(sorted(aux_filesys.split(' ')))
    ENV_VALS['CHPL_LIB_PIC'] = chpl_lib_pic.get()
    ENV_VALS['CHPL_SANITIZE'] = chpl_sanitizers.get()
    ENV_VALS['CHPL_SANITIZE_EXE'] = chpl_sanitizers.get('exe')

    # error checking that would be hard to do in the .get functions
    # due to circular dependencies
    chpl_arch.validate('host')
    chpl_arch.validate('target')
    chpl_llvm.validate_llvm_config()
    chpl_compiler.validate_compiler_settings()
    chpl_gpu.validate(ENV_VALS['CHPL_LOCALE_MODEL'], ENV_VALS['CHPL_COMM'])


"""Compute '--internal' env var values and populate global dict, ENV_VALS"""
def compute_internal_values():
    global ENV_VALS

    # Maps architecture name that Chapel uses to the name that can be included
    # in an argument like -march e.g. for gcc-4.7: 'ivybridge' -> 'core-avx-i'
    backend_info = chpl_cpu.get('target', map_to_compiler=True)
    ENV_VALS['CHPL_TARGET_CPU_FLAG'] = backend_info.flag
    ENV_VALS['CHPL_TARGET_BACKEND_CPU'] = backend_info.cpu

    ENV_VALS['CHPL_TARGET_MEM'] = chpl_mem.get('target')
    ENV_VALS['CHPL_RUNTIME_SUBDIR'] = printchplenv(set(['runtime']), print_format='path').rstrip('\n')
    ENV_VALS['CHPL_LAUNCHER_SUBDIR'] = printchplenv(set(['launcher']), print_format='path').rstrip('\n')
    ENV_VALS['CHPL_COMPILER_SUBDIR'] = printchplenv(set(['compiler']), print_format='path').rstrip('\n')
    ENV_VALS['CHPL_HOST_BIN_SUBDIR'] = chpl_bin_subdir.get('host')
    ENV_VALS['CHPL_TARGET_BIN_SUBDIR'] = chpl_bin_subdir.get('target')

    sys_modules_subdir = (chpl_platform.get('target') + "-" +
                          chpl_arch.get('target') + "-" +
                          chpl_compiler.get_path_component('target'))
    ENV_VALS['CHPL_SYS_MODULES_SUBDIR'] = sys_modules_subdir

    ENV_VALS['  CHPL_LLVM_UNIQ_CFG_PATH'] = chpl_llvm.get_uniq_cfg_path()

    ENV_VALS['  CHPL_GASNET_UNIQ_CFG_PATH'] = chpl_gasnet.get_uniq_cfg_path()

    ENV_VALS['  CHPL_GMP_UNIQ_CFG_PATH'] = chpl_gmp.get_uniq_cfg_path()

    ENV_VALS['  CHPL_HWLOC_UNIQ_CFG_PATH'] = chpl_hwloc.get_uniq_cfg_path()

    ENV_VALS['  CHPL_JEMALLOC_UNIQ_CFG_PATH'] = chpl_jemalloc.get_uniq_cfg_path('target')
    ENV_VALS['  CHPL_LIBFABRIC_UNIQ_CFG_PATH'] = chpl_libfabric.get_uniq_cfg_path()
    ENV_VALS['  CHPL_LIBUNWIND_UNIQ_CFG_PATH'] = chpl_unwind.get_uniq_cfg_path()

    ENV_VALS['  CHPL_QTHREAD_UNIQ_CFG_PATH'] = chpl_qthreads.get_uniq_cfg_path()

    ENV_VALS['  CHPL_RE2_UNIQ_CFG_PATH'] = chpl_re2.get_uniq_cfg_path()

    ENV_VALS['  CHPL_PE_CHPL_PKGCONFIG_LIBS'] = chpl_llvm.gather_pe_chpl_pkgconfig_libs()

    # compute the compiler / link args
    # each of these is bundled, system
    host_compile = ([ ], [ ])
    host_link = ([ ], [ ])
    tgt_compile = ([ ], [ ])
    tgt_link = ([ ], [ ])

    skip_host = os.environ.get('CHPLENV_SKIP_HOST', None)

    # start with arguments indicated by compiler selection

    if not skip_host:
        host_compile[0].extend(chpl_compiler.get_bundled_compile_args('host'))
        host_compile[1].extend(chpl_compiler.get_system_compile_args('host'))
        host_link[0].extend(chpl_compiler.get_bundled_link_args('host'))
        host_link[1].extend(chpl_compiler.get_system_link_args('host'))

    tgt_compile[0].extend(chpl_compiler.get_bundled_compile_args('target'))
    tgt_compile[1].extend(chpl_compiler.get_system_compile_args('target'))
    tgt_link[0].extend(chpl_compiler.get_bundled_link_args('target'))
    tgt_link[1].extend(chpl_compiler.get_system_link_args('target'))

    # add runtime includes and defines
    extend2(tgt_compile, get_runtime_includes_and_defines())
    runtime_subdir = ENV_VALS['CHPL_RUNTIME_SUBDIR']
    extend2(tgt_link, get_runtime_link_args(runtime_subdir))

    # add 3p arguments

    if (chpl_llvm.get() == 'bundled' or
        chpl_llvm.get() == 'system'):
        if not skip_host:
            extend2(host_compile, chpl_llvm.get_host_compile_args())
            extend2(host_link, chpl_llvm.get_host_link_args())

    extend2(tgt_compile, chpl_gmp.get_compile_args())
    extend2(tgt_link, chpl_gmp.get_link_args())

    extend2(tgt_compile, chpl_hwloc.get_compile_args())
    extend2(tgt_link, chpl_hwloc.get_link_args())

    if chpl_comm.get() == 'ofi':
        extend2(tgt_compile, chpl_libfabric.get_compile_args())
        extend2(tgt_link, chpl_libfabric.get_link_args())
    elif chpl_comm.get() == 'gasnet':
        extend2(tgt_compile, chpl_gasnet.get_compile_args())
        extend2(tgt_link, chpl_gasnet.get_link_args())
    elif chpl_comm.get() == 'ugni':
        # If there isn't a hugepage module loaded, we need to request
        # libhugetlbfs ourselves.
        pe_product_list = os.environ.get('PE_PRODUCT_LIST', None)
        if pe_product_list and 'HUGETLB' in pe_product_list:
            tgt_link[1].append('-lhugetlbfs')

    if chpl_tasks.get() == 'qthreads':
        extend2(tgt_compile, chpl_qthreads.get_compile_args())
        extend2(tgt_link, chpl_qthreads.get_link_args())

    extend2(tgt_compile, chpl_unwind.get_compile_args())
    extend2(tgt_link, chpl_unwind.get_link_args())

    extend2(tgt_compile, chpl_jemalloc.get_compile_args('target'))
    extend2(tgt_link, chpl_jemalloc.get_link_args('target'))
    if not skip_host:
        extend2(host_compile, chpl_jemalloc.get_compile_args('host'))
        extend2(host_link, chpl_jemalloc.get_link_args('host'))

    if chpl_re2.get() != 'none':
        extend2(tgt_compile, chpl_re2.get_compile_args())
        extend2(tgt_link, chpl_re2.get_link_args())

    aux_filesys = chpl_aux_filesys.get()
    if 'lustre' in aux_filesys:
        tgt_compile[1].append('-DSYS_HAS_LLAPI')
        tgt_link[1].append('-llustreapi')
    if 'hdfs' in aux_filesys:
        java_install = os.environ.get('JAVA_INSTALL', None)
        hadoop_install = os.environ.get('HADOOP_INSTALL', None)
        if java_install:
            java_include = os.path.join(java_install, 'include')
            tgt_compile[1].append('-I' + java_include)
            tgt_compile[1].append('-I' + os.path.join(java_include, 'linux'))
            java_lib = os.path.join(java_install, 'lib', 'amd64', 'server')
            tgt_link[1].append('-L' + java_lib)
        if hadoop_install:
            hadoop_include = os.path.join(hadoop_install, 'include')
            tgt_compile[1].append('-I' + hadoop_include)
            hadoop_lib = os.path.join(hadoop_install, 'lib', 'native')
            tgt_link[1].append('-L' + hadoop_lib)

    # remove duplicate system libraries
    host_link = (host_link[0], dedup(host_link[1]))
    tgt_link = (tgt_link[0], dedup(tgt_link[1]))

    ENV_VALS['  CHPL_HOST_BUNDLED_COMPILE_ARGS'] = " ".join(host_compile[0])
    ENV_VALS['  CHPL_HOST_SYSTEM_COMPILE_ARGS'] = " ".join(host_compile[1])
    ENV_VALS['  CHPL_HOST_BUNDLED_LINK_ARGS'] = " ".join(host_link[0])
    ENV_VALS['  CHPL_HOST_SYSTEM_LINK_ARGS'] = " ".join(host_link[1])

    ENV_VALS['  CHPL_TARGET_BUNDLED_COMPILE_ARGS'] = " ".join(tgt_compile[0])
    ENV_VALS['  CHPL_TARGET_SYSTEM_COMPILE_ARGS'] = " ".join(tgt_compile[1])
    ENV_VALS['  CHPL_TARGET_BUNDLED_LINK_ARGS'] = " ".join(tgt_link[0])
    ENV_VALS['  CHPL_TARGET_SYSTEM_LINK_ARGS'] = " ".join(tgt_link[1])


""" Returns the runtime includes and defines according
    to the current configuration, for a target (not host) compile.
    Returns tuple of (bundled_args, system_args) """
def get_runtime_includes_and_defines():
    bundled = [ ]
    system = [ ]

    incl = chpl_home_utils.get_chpl_runtime_incl()
    locale_model = chpl_locale_model.get()
    comm = chpl_comm.get();
    tasks = chpl_tasks.get()
    atomics = chpl_atomics.get()
    mem = chpl_mem.get('target')
    third_party = chpl_home_utils.get_chpl_third_party()
    platform = chpl_platform.get('target')

    bundled.append("-I" + os.path.join(incl, "localeModels", locale_model))
    bundled.append("-I" + os.path.join(incl, "localeModels"))
    bundled.append("-I" + os.path.join(incl, "comm", comm))
    bundled.append("-I" + os.path.join(incl, "comm"))
    bundled.append("-I" + os.path.join(incl, "tasks", tasks))
    bundled.append("-I" + incl)
    bundled.append("-I" + os.path.join(incl, "qio"))
    bundled.append("-I" + os.path.join(incl, "atomics", atomics))
    bundled.append("-I" + os.path.join(incl, "mem", mem))
    bundled.append("-I" + os.path.join(incl, "mem", mem))
    bundled.append("-I" + os.path.join(third_party, "utf8-decoder"))

    if platform.startswith("cygwin"):
        # w32api is provided by cygwin32-w32api-runtime
        system.append("-I" + os.path.join("usr", "include", "w32api"))

    if locale_model == "gpu":
        # this -D is needed since it affects code inside of headers
        bundled.append("-DHAS_GPU_LOCALE")
        # If compiling for GPU locales, add CUDA runtime headers to include path
        cuda_path = chpl_gpu.get_cuda_path()
        system.append("-I", os.path.join(cuda_path, "include"))

    if mem == "jemalloc":
        # set -DCHPL_JEMALLOC_PREFIX=chpl_je_
        # this is needed since it affects code inside of headers
        bundled.append("-DCHPL_JEMALLOC_PREFIX=chpl_je_")

    return (bundled, system)

""" Returns the runtime -L and -l args according
    to the current configuration, for a target (not host) compile.
    Returns tuple of (bundled_args, system_args) """
def get_runtime_link_args(runtime_subdir):
    bundled = [ ]
    system = [ ]

    lib = chpl_home_utils.get_chpl_runtime_lib()
    locale_model = chpl_locale_model.get()

    bundled.append("-L" + os.path.join(lib, runtime_subdir))
    bundled.append("-lchpl")

    if locale_model == "gpu":
        # If compiling for GPU locales, add CUDA to link path,
        # and add cuda libraries
        cuda_path = chpl_gpu.get_cuda_path()
        system.append("-L", os.path.join(cuda_path, "lib64"))
        system.append("-lcuda")
        system.append("-lcudart")

    # always link with the math library
    system.append("-lm")
    # always link with the pthreads library
    system.append("-lpthread")

    return (bundled, system)

""" Given two 2-tuples of lists, add 2nd lists to the first lists """
def extend2(x, y):
    x[0].extend(y[0])
    x[1].extend(y[1])

""" Remove duplicates, keeping last occurrence and preserving order
e.g. "-lhwloc -lqthread -lhwloc ..." -> "-lqthread -lhwloc ..."""
def dedup(args):
    seen = set()
    ret = [arg for arg in reversed(args)
           if not (arg in seen or seen.add(arg))]
    return reversed(ret)

"""Return non-empty string if var is set via environment or chplconfig"""
def user_set(env):
    env_stripped = env.strip()
    env_set = overrides.get_environ(env_stripped, '')
    config_set = overrides.get_chplconfig(env_stripped, '')
    if env_set:
        return ' *'
    elif config_set:
        return ' +'
    return ''

"""Filter out variables that are marked with NOPATH"""
def filter_path(chpl_env):
    return not 'nopath' in chpl_env.content

"""Filter variables that are not user set"""
def filter_overrides(chpl_env):
    return bool(user_set(chpl_env.name))


"""Filter variables irrelevant to configuration for --tidy flag"""
def filter_tidy(chpl_env):
    comm = ENV_VALS['CHPL_COMM']
    llvm = ENV_VALS['CHPL_LLVM']
    locale_model = ENV_VALS['CHPL_LOCALE_MODEL']
    if chpl_env.name == '  CHPL_COMM_SUBSTRATE':
        return comm == 'gasnet'
    elif chpl_env.name == '  CHPL_GASNET_SEGMENT':
        return comm == 'gasnet'
    elif chpl_env.name == '  CHPL_LIBFABRIC':
        return comm == 'ofi'
    elif chpl_env.name == '  CHPL_NETWORK_ATOMICS':
        return comm != 'none'
    elif chpl_env.name == '  CHPL_LLVM_CONFIG':
        return llvm != 'none'
    elif chpl_env.name == '  CHPL_CUDA_PATH':
        return locale_model == 'gpu'
    return True


"""Filter variables that are not selected in contents
Requires a content argument via functools.partial
"""
def _filter_content(chpl_env, contents=None):
    return chpl_env.content.intersection(contents)


"""Return string to be printed for a given variable and print_format
Requires a print_format argument
"""
def _print_var(key, value, print_format=None, shortname=None):
    key_stripped = key.strip()
    if print_format == 'pretty':
        user_set_symbol = user_set(key_stripped)
        return "{0}: {1}{2}\n".format(key, value, user_set_symbol)
    elif print_format == 'simple':
        return "{0}={1}\n".format(key_stripped, value)
    elif print_format == 'make':
        make_key = key_stripped.replace("CHPL_", "CHPL_MAKE_", 1)
        return "{0}={1}\n".format(make_key, value)
    elif print_format == 'path':
        if shortname:
            ret = "{0}-{1}".format(shortname, value)
        else:
            ret = "{0}".format(value)
        return ret + '/'
    else:
        raise ValueError("Invalid format '{0}'".format(print_format))


"""Return a string that contains the Chapel configuration variable info"""
def printchplenv(contents, print_filters=None, print_format='pretty'):
    global CHPL_ENVS

    if print_filters is None:
        print_filters = ['tidy']

    # Error checking for external python codes calling printchplenv function
    if not ENV_VALS.items:
        raise KeyError('ENV_VALS must be populated with compute_*_values()'
                       'before printchplenv is called')

    # Specialize _filter_content to use contents as default arg
    filter_content = partial(_filter_content, contents=contents)

    envs = filter(filter_content, CHPL_ENVS)

    # --path -- skip variables marked NOPATH
    if print_format == 'path':
        envs = filter(filter_path, envs)

    # --overrides
    if 'overrides' in print_filters:
        envs = filter(filter_overrides, envs)

    # --tidy
    if 'tidy' in print_filters:
        envs = filter(filter_tidy, envs)

    # Specialize _print_var to use print_format as default arg
    print_var = partial(_print_var, print_format=print_format)

    # List of strings that will be concatenated and returned
    ret = []

    # Print header
    if 'anonymize' not in print_filters:
        if print_format == 'pretty':
            ret.append("machine info: {0} {1} {2} {3} {4}\n".format(*os.uname()))
            ret.append(print_var('CHPL_HOME', ENV_VALS['CHPL_HOME']))
            this_dir = os.path.realpath(os.path.dirname(__file__))
            ret.append("script location: {0}\n".format(this_dir))
        elif print_format == 'simple':
            ret.append(print_var('CHPL_HOME', ENV_VALS['CHPL_HOME']))

    # Print environment variables and their values
    for env in envs:
        value = ENV_VALS[env.name]
        if print_format == 'path':
            if env.name == 'CHPL_TARGET_CPU':
                value = ENV_VALS['CHPL_RUNTIME_CPU']
            elif env.name == 'CHPL_COMM' and chpl_comm_debug.get() == 'debug':
                value += '-debug'
        ret.append(print_var(env.name, value, shortname=env.shortname))

    # Handle special formatting case for --path
    if print_format == 'path':
        # Remove trailing '/' and add a newline
        ret[-1] = ret[-1].rstrip('/')
        ret.append('\n')

    return ''.join(ret)


"""Define argument to parse"""
def parse_args():
    parser = optparse.OptionParser(
        usage='usage: %prog [options]',
        description = 'Print the current Chapel configuration. '
                      '[content] arguments determine what gets printed. '
                      '[filter] arguments determine what gets omitted. '
                      '[format] arguments determine how it gets printed. '
                      '[shortcut] arguments are for convenience.')

    #[shortcut]
    parser.add_option('--all', action='store_true', dest='all')

    #[content]
    parser.set_defaults(content=[])
    parser.add_option('--compiler', action='append_const', dest='content', const='compiler')
    parser.add_option('--runtime', action='append_const', dest='content', const='runtime')
    parser.add_option('--launcher', action='append_const', dest='content', const='launcher')
    parser.add_option('--internal', action='append_const', dest='content', const='internal')

    #[filter]
    parser.set_defaults(tidy=True)
    parser.set_defaults(filter=[])
    parser.add_option('--tidy', action='store_true', dest='tidy')
    parser.add_option('--no-tidy', action='store_false', dest='tidy')
    parser.add_option('--anonymize', action='append_const', dest='filter', const='anonymize')
    parser.add_option('--overrides', action='append_const', dest='filter', const='overrides')

    #[format]
    parser.set_defaults(format='pretty')
    parser.add_option('--pretty', action='store_const', dest='format', const='pretty')
    parser.add_option('--simple', action='store_const', dest='format', const='simple')
    parser.add_option('--make',   action='store_const', dest='format', const='make')
    parser.add_option('--path',   action='store_const', dest='format', const='path')

    # Hijack the help message to use the module docstring
    # optparse is not robust enough to support help msg sections for args.
    parser.print_help = lambda: stdout.write(__doc__)

    return parser.parse_args()


def main():
    (options, args) = parse_args()

    # Handle --all flag
    if options.all:
        options.content.extend(['runtime', 'launcher', 'compiler', 'default'])

    # Handle --tidy / --no-tidy flags
    if options.tidy:
        options.filter.append('tidy')

    # Set default [content]
    if not options.content:
        options.content = ['default']

    # Convert lists to sets to pass to printchplenv
    contents = set(options.content)
    filters = set(options.filter)

    # Prevent --internal --path, because it's useless
    if options.format == 'path' and 'internal' in contents:
        stdout.write('--path and --internal are incompatible flags\n')
        exit(1)

    # Populate ENV_VALS
    compute_all_values()

    # Don't populate internal ENV_VALS unless specified
    if 'internal' in contents:
        compute_internal_values()

    ret = printchplenv(contents, filters, options.format)
    stdout.write(ret)


if __name__ == '__main__':
    main()
