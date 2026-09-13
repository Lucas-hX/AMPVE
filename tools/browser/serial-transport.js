import {Transport} from 'esptool-js';

const RX_BUFFER_BYTES=65536,MAX_QUEUED_BYTES=262144,MAX_PACKET_BYTES=8192;
const fault=code=>Object.assign(new Error('USB receive failed: '+code),{code,userMessage:'USB receive failed: '+code+'. No unverified data was accepted.'});

// Keep the pinned loader, framing writer and reset strategies. The receiver uses
// a bounded linear SLIP decoder instead of reallocating the frame for every byte.
export class BufferedTransport extends Transport {
  async connect(baud=115200,options={}){
    this.receiveError=null;this.buffer=new Uint8Array();
    await super.connect(baud,{...options,bufferSize:RX_BUFFER_BYTES});
  }
  async disconnect(){
    await super.disconnect();await this.receiveTask;
  }
  readLoop(){
    if(this.receiveTask)return this.receiveTask;
    this.receiveTask=this.receive().finally(()=>{this.receiveTask=null;});
    return this.receiveTask;
  }
  async receive(){
    let reader;
    try{
      if(!this.device.readable)return;
      reader=this.device.readable.getReader();this.reader=reader;
      while(true){
        const {value,done}=await reader.read();
        if(done){this.receiveError=fault('serial_stream_closed');break;}
        if(!value?.length)continue;
        if(this.buffer.length+value.length>MAX_QUEUED_BYTES)throw fault('serial_queue_limit');
        this.buffer=this.appendArray(this.buffer,value);
      }
    }catch(error){
      const codes={BufferOverrunError:'serial_buffer_overrun',FramingError:'serial_framing_error',
        ParityError:'serial_parity_error',BreakError:'serial_break',NetworkError:'serial_disconnected'};
      this.receiveError=fault(error.code==='serial_queue_limit'?error.code:codes[error.name]||'serial_receive_error');
    }finally{
      reader?.releaseLock();if(this.reader===reader)this.reader=undefined;
    }
  }
  async read(timeout){
    const packet=new Uint8Array(MAX_PACKET_BYTES),deadline=performance.now()+timeout;
    let started=false,escaping=false,length=0;
    while(true){
      if(this.receiveError)throw this.receiveError;
      if(performance.now()>=deadline)throw fault('serial_packet_timeout');
      if(!this.buffer.length){await new Promise(resolve=>setTimeout(resolve,1));continue;}
      const bytes=this.buffer;this.buffer=new Uint8Array();
      for(let i=0;i<bytes.length;i++){
        let byte=bytes[i];
        if(!started){if(byte!==0xc0)throw fault('serial_packet_head');started=true;continue;}
        if(escaping){
          if(byte===0xdc)byte=0xc0;else if(byte===0xdd)byte=0xdb;else throw fault('serial_packet_escape');
          escaping=false;
        }else if(byte===0xdb){escaping=true;continue;}
        else if(byte===0xc0){
          // Empty delimiter runs synchronize SLIP; they are not flash data packets.
          if(!length)continue;
          this.buffer=bytes.subarray(i+1);
          return packet.slice(0,length);
        }
        if(length===MAX_PACKET_BYTES)throw fault('serial_packet_limit');
        packet[length++]=byte;
      }
    }
  }
}
