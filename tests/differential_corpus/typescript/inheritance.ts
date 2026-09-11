// Inheritance: extends, super, abstract classes, overrides.

abstract class Animal {
  constructor(protected name: string) {}

  abstract speak(): string;

  describe(): string {
    return `animal:${this.name}`;
  }
}

class Dog extends Animal {
  constructor(name: string, private breed: string) {
    super(name);
  }

  speak(): string {
    return `${super.describe()} (woof)`;
  }

  fetch(): string {
    return `${this.name} fetches`;
  }
}

class Puppy extends Dog {
  constructor(name: string) {
    super(name, "mixed");
  }

  speak(): string {
    return `${super.speak()} (yip)`;
  }
}

interface Runner {
  speed(): number;
}

class Greyhound extends Dog implements Runner {
  speed(): number {
    return 45;
  }
}

const rex = new Puppy("Rex");