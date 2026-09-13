// esptool-js 0.6.1 HardReset only releases RTS. Use its maintained custom strategy
// to drive a complete EN pulse with the download strap released on the 7B bridge.
export const APPLICATION_RESET_SEQUENCE='D0|R1|W100|R0|W100|D0';
export async function resetApplication(reader){
  await reader.loader.after('custom_reset',false,APPLICATION_RESET_SEQUENCE);
}
