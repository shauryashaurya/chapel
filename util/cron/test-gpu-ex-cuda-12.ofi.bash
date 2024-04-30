#!/usr/bin/env bash
#
# GPU native testing on a Cray EX

CWD=$(cd $(dirname ${BASH_SOURCE[0]}) ; pwd)
source $CWD/common-native-gpu.bash
source $CWD/common-hpe-cray-ex.bash

module load cudatoolkit/23.3_12.0  # this is the default on this system

export CHPL_LLVM=bundled  # CUDA 12 is only supported with bundled LLVM
export CHPL_COMM=ofi
export CHPL_LOCALE_MODEL=gpu
export CHPL_LAUNCHER_PARTITION=allgriz
export CHPL_GPU=nvidia  # amd is also detected automatically

export CHPL_NIGHTLY_TEST_CONFIG_NAME="gpu-ex-cuda-12.ofi"
$CWD/nightly -cron ${nightly_args}
