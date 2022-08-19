class C {
  var x : int = 1;
}

class D : C {
  var y : real = 2.0;
}

proc foo(c : borrowed C) {
  writeln(c.x);
}

var c : borrowed C = (new owned C(), d : borrowed D = new borrowed D()).borrow();

writeln(c);
writeln(d);

foo(c);
foo(d);
