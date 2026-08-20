package ingest

import (
	"strings"
	"testing"
)

func TestDecodeOTLPJSON(t *testing.T) {
	payload := `{"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"checkout"}}]},"scopeSpans":[{"spans":[{"name":"GET /users/{id}","startTimeUnixNano":"1000000","endTimeUnixNano":"4000000","attributes":[{"key":"peer.service","value":{"stringValue":"users"}},{"key":"http.route","value":{"stringValue":"/users/{id}"}},{"key":"http.request.method","value":{"stringValue":"GET"}},{"key":"contract.fields","value":{"stringValue":"id,email"}}]}]}]}]}`
	got, err := DecodeOTLPJSON(strings.NewReader(payload))
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 {
		t.Fatalf("got %d observations", len(got))
	}
	if got[0].Consumer != "checkout" || got[0].Provider != "users" || got[0].LatencyMS != 3 {
		t.Fatalf("unexpected: %#v", got[0])
	}
	if len(got[0].Fields) != 2 {
		t.Fatalf("fields: %#v", got[0].Fields)
	}
}

func TestDecodeRejectsInvalidJSON(t *testing.T) {
	if _, err := DecodeOTLPJSON(strings.NewReader("{")); err == nil {
		t.Fatal("expected error")
	}
}
