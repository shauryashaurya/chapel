
use BlockDist;

config const size : int = 8;
const sizeRange = 0..#(size : int(64));


const myBlockDist = new blockDist(rank=1, idxType=int(64), boundingBox={sizeRange});
const blockDom : domain(1, int(64)) dmapped myBlockDist = {sizeRange};

var array : [blockDom] int(64) = [i in blockDom] i;
var output : [blockDom] string;

forall i in array.domain with (ref output) {
  for j in 1..array(i) {
    output[i] += j:string + " ";
    if (j == 5) then {
      output[i] += "...";
      break; // this used to cause an error; not anymore.
    }
  }
  output[i] += ".";
}

for s in output do
   writeln(s);

