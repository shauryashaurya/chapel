/*
Note for comparisons against .good :

The taskId values generated by nextLocalTaskCounter()
currently depend on the structure of the Block domain iterator,
which may change.

The observed behavior is correct when the number of tasks,
i.e. the number of different values of taskId, as printed by
writef("t1..."), equals 'dptpl' on each locale.
*/

use BlockDist, PrivateDist;

config const numMessages = 36;
config const dptpl = 3;

var taskCounters: [PrivateSpace] atomic int;
taskCounters.write(1);
proc nextLocalTaskCounter(hereId:int) {
  return taskCounters[hereId].fetchAdd(1);
}

const MessageDom = {1..numMessages};
const MessageSpace = MessageDom dmapped Block(MessageDom,
                                              dataParTasksPerLocale = dptpl);

var MessageVisited: [MessageSpace] bool;

// Ensure correct amount of TPVs on each locale.

forall msg in MessageSpace with (const taskId = nextLocalTaskCounter(here.id)) {
  writef("t1  loc %i  task %i\n", here.id, taskId);
  MessageVisited[msg] ^= true;
}

assert(& reduce MessageVisited);
taskCounters.write(1);

// Ensure each TPV stays with its task.

forall msg in MessageSpace with (var taskId = nextLocalTaskCounter(here.id)*100)
{
  taskId += 1;
  writef("t2  loc %i  task %i\n", here.id, taskId);
  MessageVisited[msg] ^= true;
}

assert(!(| reduce MessageVisited));
