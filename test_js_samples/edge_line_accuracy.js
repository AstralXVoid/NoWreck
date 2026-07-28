// This file tests line number accuracy.
// Tree-sitter row indices are 0-based; scanner adds 1 to produce 1-based line numbers.

function line4() {}          // ← tree-sitter row 3, scanner reports line 4

const line6 = () => {};      // ← tree-sitter row 5, scanner reports line 6

class Line8 {                // ← tree-sitter row 7, scanner reports line 8
    line9() {}               // ← tree-sitter row 8, scanner reports line 9
    line10() {}              // ← tree-sitter row 9, scanner reports line 10
}

export function line13() {}  // ← tree-sitter row 12, scanner reports line 13

export class Line15 {        // ← tree-sitter row 14, scanner reports line 15
    line16() {}              // ← tree-sitter row 15, scanner reports line 16
    line17() {}              // ← tree-sitter row 16, scanner reports line 17
}

export const line20 = () => {};  // ← tree-sitter row 19, scanner reports line 20


// Two blank lines above; line 24:
function line24() {}          // ← tree-sitter row 23, scanner reports line 24
