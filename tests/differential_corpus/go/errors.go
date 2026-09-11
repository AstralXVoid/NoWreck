// Error handling: error returns, wrapped errors, custom error types.
package config

type ConfigError struct {
	Field string
	Msg   string
}

func (e *ConfigError) Error() string {
	return e.Field + ": " + e.Msg
}

func ParseConfig(raw string) (map[string]string, error) {
	if len(raw) == 0 {
		return nil, &ConfigError{Field: "root", Msg: "empty config"}
	}
	result := make(map[string]string)
	for _, line := range strings.Split(raw, "\n") {
		if line == "" {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			return nil, &ConfigError{Field: "line", Msg: line}
		}
		result[strings.TrimSpace(parts[0])] = strings.TrimSpace(parts[1])
	}
	return result, nil
}

func LoadConfig(path string) (map[string]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}
	return ParseConfig(string(data))
}

func ModeOrDefault(cfg map[string]string) string {
	if mode, ok := cfg["mode"]; ok {
		return mode
	}
	return "dev"
}

func MustLoad(path string) map[string]string {
	cfg, err := LoadConfig(path)
	if err != nil {
		panic(err)
	}
	return cfg
}
