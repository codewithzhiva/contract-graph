package ingest

import (
	"encoding/json"
	"fmt"
	"io"
	"strings"
)

type Observation struct {
	Consumer   string   `json:"consumer"`
	Provider   string   `json:"provider"`
	Route      string   `json:"route"`
	Method     string   `json:"method"`
	StatusCode int      `json:"status_code"`
	LatencyMS  float64  `json:"latency_ms"`
	Fields     []string `json:"fields"`
}

// DecodeOTLPJSON extracts a privacy-safe dependency sketch from the official
// OTLP/HTTP JSON envelope. Attribute values are used only for routing metadata;
// request and response bodies are never retained.
func DecodeOTLPJSON(r io.Reader) ([]Observation, error) {
	var envelope map[string]any
	dec := json.NewDecoder(io.LimitReader(r, 8<<20))
	if err := dec.Decode(&envelope); err != nil {
		return nil, fmt.Errorf("decode OTLP JSON: %w", err)
	}
	resources, _ := envelope["resourceSpans"].([]any)
	var out []Observation
	for _, rawResource := range resources {
		resource, _ := rawResource.(map[string]any)
		service := attrs(attributeList(resource, "resource"))["service.name"]
		for _, rawScope := range array(resource, "scopeSpans") {
			scope, _ := rawScope.(map[string]any)
			for _, rawSpan := range array(scope, "spans") {
				span, _ := rawSpan.(map[string]any)
				a := attrs(array(span, "attributes"))
				provider := first(a["peer.service"], a["server.address"], a["net.peer.name"])
				route := first(a["http.route"], a["url.path"], stringValue(span["name"]))
				method := strings.ToUpper(first(a["http.request.method"], a["http.method"], "GET"))
				if service == "" || provider == "" || route == "" {
					continue
				}
				out = append(out, Observation{
					Consumer: service, Provider: provider, Route: route, Method: method,
					StatusCode: intValue(first(a["http.response.status_code"], a["http.status_code"])),
					LatencyMS:  durationMS(span), Fields: splitFields(a["contract.fields"]),
				})
			}
		}
	}
	return out, nil
}

func durationMS(span map[string]any) float64 {
	start, end := int64Value(span["startTimeUnixNano"]), int64Value(span["endTimeUnixNano"])
	if end <= start {
		return 0
	}
	return float64(end-start) / 1e6
}

func attributeList(m map[string]any, key string) []any {
	v, _ := m[key].(map[string]any)
	return array(v, "attributes")
}

func array(m map[string]any, key string) []any {
	v, _ := m[key].([]any)
	return v
}

func attrs(values []any) map[string]string {
	out := map[string]string{}
	for _, raw := range values {
		item, _ := raw.(map[string]any)
		key, _ := item["key"].(string)
		value, _ := item["value"].(map[string]any)
		for _, candidate := range []string{"stringValue", "intValue", "doubleValue", "boolValue"} {
			if v, ok := value[candidate]; ok {
				out[key] = stringValue(v)
				break
			}
		}
	}
	return out
}

func splitFields(v string) []string {
	seen, out := map[string]bool{}, []string{}
	for _, field := range strings.Split(v, ",") {
		field = strings.TrimSpace(field)
		if field != "" && !seen[field] {
			seen[field] = true
			out = append(out, field)
		}
	}
	return out
}

func first(values ...string) string {
	for _, v := range values {
		if v != "" {
			return v
		}
	}
	return ""
}

func stringValue(v any) string { return fmt.Sprint(v) }
func intValue(v string) int    { var n int; _, _ = fmt.Sscan(v, &n); return n }
func int64Value(v any) int64   { var n int64; _, _ = fmt.Sscan(stringValue(v), &n); return n }
