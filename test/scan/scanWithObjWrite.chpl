use BlockDist;

var A = Block.createArray({1..10}, real);
A = 1.0;
var B = + scan A;

proc foo() {
  writeln("In foo");
  return 42;
}

var o: object = new object();
writeln("o is: " + o:string);
writeln("B is: ", B);
