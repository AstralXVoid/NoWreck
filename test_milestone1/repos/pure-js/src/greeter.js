// Greeting utilities.

function greet(name) {
  var message = formatGreeting("Hello", name);
  console.log(message);
  return message;
}

const formatGreeting = (template, name) => {
  return template + ", " + name + "!";
};

const farewell = (name) => {
  var msg = "Goodbye, " + name + "!";
  console.log(msg);
  return msg;
};
