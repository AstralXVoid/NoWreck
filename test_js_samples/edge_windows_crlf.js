// Edge case 12: Windows-style line endings (\r\n)
// This file should be checked with actual \r\n line endings if possible
function windowsStyle() {
    return "crlf";
}

class WinClass {
    winMethod() {
        return "win";
    }
}

export const winArrow = () => {
    return "arrow";
};
