// Edge case 4: Async functions and generators (generators deferred)
async function fetchData(url) {
    const response = await fetch(url);
    return response.json();
}

const processAsync = async (data) => {
    return data.map(x => x * 2);
};

// Generator function — should be captured per normal function rules
function* generateIds() {
    let id = 0;
    while (true) {
        yield id++;
    }
}

// Async generator — similar
async function* streamResults(query) {
    for await (const row of query) {
        yield row;
    }
}
