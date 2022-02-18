module A {
  proc f() { writeln("A.f"); }
  var x = "A";
}
module B {
  proc f() { writeln("B.f"); }
  var x = "B";
}

module CUseA {
  public use A;
  proc f() { writeln("C.f"); }
  var x = "C";
}

module UseA_UseB {
  public use A;
  public use B;
}

module UseB {
  public use B;
}

module UseA_UseUseB {
  public use A;
  public use UseB;
}

module CUseA_UseA {
  public use CUseA;
  public use A;
}

module CUseA_ImportA {
  public use CUseA;
  import A;
}

module Program {
  use UseA_UseUseB;  // -> ambiguity between A.f and B.f
                     // -> x refers to A.x

  proc main() {
    f();
  }
}
