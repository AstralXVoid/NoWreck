// JavaScript utility functions (mirrors utils.py functionality)


function validateEmail(email) {
  if (email.includes("@") && email.includes(".")) {
    var parts = email.split("@");
    if (parts.length === 2 && parts[1].split(".").length >= 2) {
      console.log("Validated: " + email);
      return true;
    }
  }
  return false;
}


function formatDate(year, month, day) {
  return year + "-" + pad(month) + "-" + pad(day);
}


function pad(n) {
  return n < 10 ? "0" + n : String(n);
}
