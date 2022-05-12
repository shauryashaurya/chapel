// see also issue #19160
module M {
  var x: int = 1;
}

module N {
  private import M.x;
  var x: int = 2;

  proc main() {
    writeln(x);
  }
}
