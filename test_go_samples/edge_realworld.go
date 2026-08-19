package main

import (
    "context"
    "errors"
    "net/http"
)

// Real-world Go patterns — HTTP handlers, middleware, errors, context.

// Custom error type
type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return e.Field + ": " + e.Message
}

// HTTP handler function
func handleUser(w http.ResponseWriter, r *http.Request) {
    w.WriteHeader(http.StatusOK)
}

// HTTP handler method
type Server struct {
    addr string
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
    w.WriteHeader(http.StatusOK)
}

// Middleware pattern
func LoggingMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        next.ServeHTTP(w, r)
    })
}

// Function with error wrapping
func loadConfig(path string) (*Config, error) {
    if path == "" {
        return nil, errors.New("empty path")
    }
    return &Config{Name: path}, nil
}

// Function with context
func FetchWithContext(ctx context.Context, url string) (string, error) {
    select {
    case <-ctx.Done():
        return "", ctx.Err()
    default:
        return "ok", nil
    }
}

// Generic error handler
func handleError(err error) string {
    var ve *ValidationError
    if errors.As(err, &ve) {
        return ve.Message
    }
    return "unknown error"
}

// Config struct
type Config struct {
    Name string
}

// Interface with multiple methods
type Handler interface {
    ServeHTTP(w http.ResponseWriter, r *http.Request)
    Validate(r *http.Request) error
}

// Type alias
type HandlerFunc = func(http.ResponseWriter, *http.Request)

// Const group (not captured as symbols — only items with names)
const (
    StatusOK    = 200
    StatusError = 500
)
