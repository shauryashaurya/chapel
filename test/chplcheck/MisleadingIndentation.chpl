module Indentation {
  for i in 1..10 do
    writeln(i);
    writeln("second thing");

  @chplcheck.ignore("MisleadingIndentation")
  for i in 1..10 do
    writeln(i);
    writeln("second thing");

  for i in 1..10 do
writeln(i);
writeln("second thing");

  // the only fixit is ignore, cant apply fixit to the multiline
  for i in 1..10 do
    writeln(i);
    writeln
    ("second thing");

  // the only fixit here is ignore, don't know the indentation level
  for i in 1..10 do
  writeln(i);
  writeln("second thing");

}
