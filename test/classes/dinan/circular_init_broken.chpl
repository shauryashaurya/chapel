class C {
  var a: int = b+1;
  var b: int = a-1;
}

var c: borrowed C = (new owned C(1)).borrow();

writeln("a=", c.a, " b=", c.b);
