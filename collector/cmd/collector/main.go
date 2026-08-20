package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/codewithzhiva/contract-graph/collector/internal/ingest"
)

var accepted atomic.Uint64
var rejected atomic.Uint64

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	upstream := env("CONTROL_PLANE_URL", "http://localhost:8000")
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { jsonResponse(w, 200, map[string]string{"status": "ok"}) })
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		jsonResponse(w, 200, map[string]string{"status": "ready"})
	})
	mux.HandleFunc("/metrics", metrics)
	mux.HandleFunc("/v1/traces", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", 405)
			return
		}
		observations, err := ingest.DecodeOTLPJSON(r.Body)
		if err != nil {
			rejected.Add(1)
			jsonResponse(w, 400, map[string]string{"error": err.Error()})
			return
		}
		body, _ := json.Marshal(map[string]any{"observations": observations})
		req, _ := http.NewRequestWithContext(r.Context(), http.MethodPost, upstream+"/v1/runtime/observations", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			rejected.Add(1)
			jsonResponse(w, 503, map[string]string{"error": "control plane unavailable"})
			return
		}
		defer resp.Body.Close()
		if resp.StatusCode >= 300 {
			rejected.Add(1)
			jsonResponse(w, 502, map[string]string{"error": "control plane rejected observations"})
			return
		}
		accepted.Add(uint64(len(observations)))
		jsonResponse(w, 202, map[string]any{"accepted": len(observations)})
	})

	server := &http.Server{Addr: env("LISTEN_ADDR", ":4318"), Handler: requestLog(log, mux), ReadHeaderTimeout: 5 * time.Second}
	go func() {
		log.Info("collector listening", "addr", server.Addr)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error("server failed", "error", err)
			os.Exit(1)
		}
	}()
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = server.Shutdown(ctx)
}

func metrics(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	fmt.Fprintf(w, "contractgraph_observations_accepted_total %d\ncontractgraph_batches_rejected_total %d\n", accepted.Load(), rejected.Load())
}
func requestLog(log *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		log.Info("request", "method", r.Method, "path", r.URL.Path, "duration_ms", time.Since(start).Milliseconds())
	})
}
func jsonResponse(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
