use List;

var s1 : list(int) = makeList( 3, 1, 4, 1, 5, 9 );
var s2 : list(int);

writeln(s1);

s2 = s1;
writeln(s2);

s1.destroy();
