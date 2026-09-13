import { ESPLoader, Transport } from 'esptool-js';

// Inspection uses ROM sync and register reads only: never main(), stubs or flash APIs.
export async function inspectPort(port, Loader = ESPLoader, SerialTransport = Transport) {
  const transport = new SerialTransport(port, false);
  const quiet = {clean(){}, writeLine(){}, write(){}};
  const loader = new Loader({transport, baudrate:115200, terminal:quiet, debugLogging:false});
  let timer;
  try {
    const operation = async () => {
      await loader.connect('default_reset', 3, true);
      const chip = loader.chip.CHIP_NAME;
      const description = chip === 'ESP32-P4' ? await loader.chip.getChipDescription(loader) : chip;
      await loader.after('hard_reset');
      return {chip, description};
    };
    return await Promise.race([operation(), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('Inspection timeout')), 30000);
    })]);
  } finally {
    clearTimeout(timer);
    await transport.disconnect();
  }
}

const select = document.querySelector('#select-usb');
if (select) {
  const form = document.querySelector('#inspect-device');
  const inspect = document.querySelector('#inspect-chip');
  const usbStatus = document.querySelector('#usb-status');
  const chipStatus = document.querySelector('#chip-status');
  let port, busy = false;
  if (!('serial' in navigator)) {
    select.disabled = true;
    usbStatus.textContent = 'Web Serial is unavailable here. Open ampve.com in desktop Chrome or Edge.';
  } else {
    select.addEventListener('click', async () => {
      try {
        // No vendor filter: a USB-to-UART bridge may have a different vendor ID.
        port = await navigator.serial.requestPort();
        const info = port.getInfo();
        const hex = value => value === undefined ? 'unknown' : '0x' + value.toString(16).padStart(4,'0');
        usbStatus.textContent = `Port selected · USB vendor ${hex(info.usbVendorId)}, product ${hex(info.usbProductId)}. Board model not confirmed.`;
        chipStatus.textContent = 'Ready for chip inspection. Confirm the restart notice first.';
        inspect.disabled = false;
      } catch {
        usbStatus.textContent = 'No new port selected. Check the cable and browser permission, then retry.';
      }
    });
    navigator.serial.addEventListener('disconnect', event => {
      if (event.target === port && !busy) {
        port = null; inspect.disabled = true;
        usbStatus.textContent = 'Selected USB device disconnected.';
      }
    });
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!port || busy) return;
    busy = true; select.disabled = true; inspect.disabled = true;
    chipStatus.textContent = 'Inspecting the chip. The board may restart; allow up to 30 seconds…';
    try {
      const result = await inspectPort(port);
      chipStatus.textContent = result.chip === 'ESP32-P4'
        ? `${result.description} detected. Confirm the Waveshare 7B label separately. Flash size, partitions and firmware compatibility still require an audit. Nothing was installed or paired.`
        : `${result.description} detected. This is not the ESP32-P4 required by the current board profile. Nothing was installed or paired.`;
    } catch {
      chipStatus.textContent = 'Inspection failed. Close serial monitors, verify the programming port and data cable. If needed, use BOOT/RESET as described by Waveshare and retry. Press RESET or reconnect power to resume the original firmware. No firmware write was requested.';
    } finally {
      busy = false; select.disabled = false; inspect.disabled = !port;
    }
  });
}
