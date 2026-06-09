package main

import (
	"errors"
	"testing"
	"time"
)

func TestBridgeStateSendStatusDistinguishesLoggedOutAndReconnecting(t *testing.T) {
	state := NewBridgeState()

	if ok, msg := state.SendStatus(false); ok || msg != "reconnecting to WhatsApp" {
		t.Fatalf("disconnected SendStatus = (%v, %q), want reconnecting failure", ok, msg)
	}

	state.SetLoggedOut()
	if ok, msg := state.SendStatus(false); ok || msg != "logged out from WhatsApp - re-pair needed" {
		t.Fatalf("logged out SendStatus = (%v, %q), want re-pair failure", ok, msg)
	}
	if ok, msg := state.SendStatus(true); ok || msg != "logged out from WhatsApp - re-pair needed" {
		t.Fatalf("logged out connected SendStatus = (%v, %q), want re-pair failure", ok, msg)
	}

	state.SetConnected()
	if ok, msg := state.SendStatus(true); !ok || msg != "" {
		t.Fatalf("connected SendStatus = (%v, %q), want success", ok, msg)
	}
}

func TestReconnectManagerRetriesWithBackoffUntilConnected(t *testing.T) {
	state := NewBridgeState()
	attempts := 0
	var slept []time.Duration

	manager := NewReconnectManager(state, ReconnectConfig{
		Connect: func() error {
			attempts++
			if attempts < 3 {
				return errors.New("temporary disconnect")
			}
			return nil
		},
		HasSession: func() bool { return true },
		Sleep:      func(d time.Duration) { slept = append(slept, d) },
		MinBackoff: time.Second,
		MaxBackoff: 4 * time.Second,
		Jitter:     func(time.Duration) time.Duration { return 0 },
	})

	manager.runReconnectLoop("test disconnect")

	if attempts != 3 {
		t.Fatalf("attempts = %d, want 3", attempts)
	}
	if len(slept) != 2 || slept[0] != time.Second || slept[1] != 2*time.Second {
		t.Fatalf("slept = %v, want [1s 2s]", slept)
	}
	if state.IsReconnecting() {
		t.Fatal("state is still reconnecting after successful reconnect")
	}
}

func TestReconnectManagerDoesNotReconnectLoggedOutSession(t *testing.T) {
	state := NewBridgeState()
	state.SetLoggedOut()
	attempts := 0

	manager := NewReconnectManager(state, ReconnectConfig{
		Connect: func() error {
			attempts++
			return nil
		},
		HasSession: func() bool { return true },
		Sleep:      func(time.Duration) {},
		MinBackoff: time.Second,
		MaxBackoff: time.Second,
		Jitter:     func(time.Duration) time.Duration { return 0 },
	})

	manager.runReconnectLoop("test disconnect")

	if attempts != 0 {
		t.Fatalf("attempts = %d, want no reconnect for logged-out session", attempts)
	}
}
