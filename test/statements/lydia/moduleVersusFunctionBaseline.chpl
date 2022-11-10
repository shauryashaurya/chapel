use Time;
// Baseline: addition/subtraction, with similar < > comparisons

config const numIters = 100000;
config const numTrials = 100;
config const verbose = false;

var res1 = 0;
var t1: stopwatch;

t1.start();
for i in 1..#numTrials {
  for j in 1..#numIters {
    if (j < i) {
      res1 += j;
    } else {
      res1 -= j;
    }
  }
}
t1.stop();
method();

proc method() {
  var res2 = 0;
  var t2: stopwatch;
  t2.start();
  for i in 1..#numTrials {
    for j in 1..#numIters {
      if (j < i) {
        res2 += j;
      } else {
        res2 -= j;
      }
    }
  }
  t2.stop();
  if (res1 != res2) {
    writeln("Error, res1 did not match res2!");
  } else {
    writeln("Success!");
  }
  if verbose {
    writeln ("Module level access took ",
             t1.elapsed(TimeUnits.milliseconds)/1000);
    writeln ("Method level access took ",
             t2.elapsed(TimeUnits.milliseconds)/1000);
  }
}

