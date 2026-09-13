import {ImprovSerial} from 'improv-wifi-serial-sdk/dist/serial.js';
// The SDK's diagnostic logger includes raw Wi-Fi packets. Never retain or print them.
const quiet=Object.freeze({log(){},debug(){},error(){}});
export function validCredentials(ssid,password){
  const bytes=new TextEncoder();
  return typeof ssid==='string'&&typeof password==='string'&&!ssid.includes('\0')&&!password.includes('\0')&&
    bytes.encode(ssid).length>=1&&bytes.encode(ssid).length<=32&&bytes.encode(password).length<=64;
}
export async function openWifi(port,onState=()=>{}){
  let serial,connected=true,opened=false;
  try{
    await port.open({baudRate:115200});opened=true;
    serial=new ImprovSerial(port,quiet);
    serial.addEventListener('state-changed',()=>onState(serial.state));
    serial.addEventListener('disconnect',()=>{connected=false;onState(undefined);});
    const info=await serial.initialize(15000);
    if(info?.firmware!=='AMPVE'||info.chipFamily!=='waveshare-p4-7b')throw new Error('Unsupported firmware');
    return {
      info:Object.freeze({firmware:info.firmware,version:info.version,chipFamily:info.chipFamily}),
      get state(){return connected?serial.state:undefined;},
      async provision(ssid,password){
        if(!connected||serial.state!==2||!validCredentials(ssid,password))throw new Error('Setup unavailable');
        await serial.provision(ssid,password,90000);
        if(serial.state!==4)throw new Error('Connection not confirmed');
        // Device-supplied URLs are deliberately unused. Account pairing stays in this page.
      },
      async close(){await serial.close();await port.close();},
    };
  }catch(error){
    if(serial)await serial.close().catch(()=>{});
    if(opened)await port.close().catch(()=>{});
    throw new Error('USB Wi-Fi setup unavailable');
  }
}
