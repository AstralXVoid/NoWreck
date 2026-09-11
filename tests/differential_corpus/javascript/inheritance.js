// Inheritance: extends, super calls, overrides.

class Animal {
  constructor(name) {
    this.name = name;
  }

  speak() {
    return `${this.name} makes a sound`;
  }

  describe() {
    return `animal:${this.name}`;
  }
}

class Dog extends Animal {
  constructor(name, breed) {
    super(name);
    this.breed = breed;
  }

  speak() {
    return `${super.speak()} (woof)`;
  }

  fetch() {
    return `${this.name} fetches`;
  }
}

class Puppy extends Dog {
  constructor(name) {
    super(name, "mixed");
  }

  speak() {
    return `${super.speak()} (yip)`;
  }
}

const rex = new Puppy("Rex");