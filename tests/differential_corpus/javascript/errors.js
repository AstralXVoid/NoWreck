// Error handling: throw, try/catch/finally, custom errors.

class ConfigError extends Error {
  constructor(message, configKey) {
    super(message);
    this.name = "ConfigError";
    this.configKey = configKey;
  }
}

function parseConfig(raw) {
  if (typeof raw !== "string" || raw.trim() === "") {
    throw new ConfigError("empty config", "root");
  }
  const result = {};
  for (const line of raw.split("\n")) {
    const [key, value] = line.split("=");
    result[key.trim()] = value.trim();
  }
  return result;
}

function loadWithFallback(raw, fallback) {
  try {
    return parseConfig(raw);
  } catch (error) {
    console.warn(`falling back: ${error.message}`);
    return fallback;
  } finally {
    console.info("attempt finished");
  }
}

function assertValid(config) {
  if (!config.mode) {
    throw new TypeError("mode required");
  }
  return config;
}