// Collects microphone samples for SAARTHI's on-node speech recognition (no audio leaves the node).
class NirantarRecorder extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("nirantar-recorder", NirantarRecorder);
