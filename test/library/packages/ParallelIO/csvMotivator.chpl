use ParallelIO, IO, Random;

const fileName = "colors.csv";

config const n = 1000,
             tpl = 4;

proc main() {
  var c1 = makeRandomCSVFile(fileName, n),
      c2 = readParallelDelimited(fileName, t=color, tasksPerLoc=tpl, skipHeaderLines=1);

  assert(c2.size == n);
  for (j1, j2, i) in zip(c1, c2, 0..) {
    if j1 != j2 {
      writeln("mismatch at ", i, ": [", j1, "] != [", j2, "]");
    }
  }
}

var rng = new RandomStream(uint(8));

record color: serializable {
  var r, g, b: uint(8);

  proc init() {
    this.r = 0;
    this.g = 0;
    this.b = 0;
  }

  proc init(r: uint(8), g: uint(8), b: uint(8)) {
    this.r = r;
    this.g = g;
    this.b = b;
  }
};

proc ref color.deserialize(reader: fileReader(?), ref deserializer) throws {
  reader.read(this.r);
  reader.readLiteral(b",");
  reader.read(this.g);
  reader.readLiteral(b",");
  reader.read(this.b);
}

proc color.serialize(writer: fileWriter(?), ref serializer) throws {
  writer.write(this.r);
  writer.writeLiteral(b",");
  writer.write(this.g);
  writer.writeLiteral(b",");
  writer.write(this.b);
}

proc type color.random(): color {
  return new color(
    rng.getNext(),
    rng.getNext(),
    rng.getNext()
  );
}

proc makeRandomCSVFile(path: string, n: int): [] color throws {
  var f = open(path, ioMode.cwr),
      w = f.writer(locking=false),
      colors: [0..<n] color;

  w.writeln("r,g,b");

  for i in 0..<n {
    const c = color.random();
    w.writeln(c);
    colors[i] = c;
  }

  return colors;
}
