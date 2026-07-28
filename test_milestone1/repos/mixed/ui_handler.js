// UI handler — calls JS utilities and coordinates rendering

import { validateEmail, formatDate } from "./utils.js";


class UiHandler {
  constructor(rootElement) {
    this.root = rootElement;
    this.logger = new Logger("UI");
  }

  renderUser(username, email) {
    var valid = validateEmail(email);
    var status = valid ? "valid" : "invalid";
    var output = "User " + username + " (" + email + ") is " + status;
    this.logger.log(output);
    return output;
  }

  renderDate(year, month, day) {
    var formatted = formatDate(year, month, day);
    var output = "Date: " + formatted;
    console.log(output);
    return output;
  }
}


function Logger(prefix) {
  this.prefix = prefix;
}

Logger.prototype.log = function(message) {
  var output = "[" + this.prefix + "] " + message;
  console.log(output);
  return output;
};
