// Edge case 4: Async functions and generators

// Async function (always worked)
async function fetchData(url) {
    const response = await fetch(url);
    return response.json();
}

// Async arrow function (always worked)
const processAsync = async (data) => {
    return data.map(x => x * 2);
};

// Generator function — now captured (v4)
function* generateIds() {
    let id = 0;
    while (true) {
        yield id++;
    }
}

// Async generator — now captured (v4)
async function* streamResults(query) {
    for await (const row of query) {
        yield row;
    }
}

// Generator expression assigned to const — now captured (v4)
const makeRange = function*(start, end) {
    while (start < end) {
        yield start++;
    }
};
