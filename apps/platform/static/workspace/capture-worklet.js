/* Browser-only development capture. Audio is never stored. */
class CapturePCM extends AudioWorkletProcessor {
  constructor() { super(); this.samples = new Int16Array(480); this.position = 0; }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    for (const value of input) {
      this.samples[this.position++] = Math.max(-1, Math.min(1, value)) * 32767;
      if (this.position === this.samples.length) {
        this.port.postMessage(this.samples.buffer, [this.samples.buffer]);
        this.samples = new Int16Array(480); this.position = 0;
      }
    }
    return true;
  }
}
registerProcessor('ampve-capture', CapturePCM);
