import {CONTRACT,HARDWARE_PROFILE} from './profile.js';
const hash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const integer=(value,max=HARDWARE_PROFILE.resources.flash_bytes)=>Number.isSafeInteger(value)&&value>=0&&value<=max;
function require(value){if(!value)throw new Error('Verified backup summary unavailable');}
export function reviewSummary(report,source){
  require(['live-browser-capture','imported-capture-record'].includes(source));
  require(report?.schema===1&&report.matching_files===true&&report.independent_reads_match===true&&hash(report.sha256)&&hash(report.table_sha256));
  require(report.flash_bytes===HARDWARE_PROFILE.resources.flash_bytes&&integer(report.partition_table_offset));
  require(report.partition_table_md5_verified===true&&Array.isArray(report.partitions)&&report.partitions.length<=128&&Array.isArray(report.images)&&report.images.length<=129);
  const partitions=report.partitions.map((p,index)=>{
    for(const key of ['type','subtype','offset','size','flags'])require(integer(p[key],key==='flags'?0xffffffff:report.flash_bytes));
    require(p.offset+p.size<=report.flash_bytes);
    // Names and all other strings from flash stay private.
    return {index,type:p.type,subtype:p.subtype,offset:p.offset,size:p.size,flags:p.flags};
  });
  const images=report.images.map((p,index)=>{
    const result={index,role:['bootloader','factory','ota_0','ota_1'].includes(p.name)?p.name:'other-application',erased:p.erased===true};
    if(result.erased)return result;
    for(const key of ['offset','image_bytes','chip_id','min_revision','max_revision'])require(integer(p[key]));
    require(p.internal_checksum_verified===true&&p.appended_sha256_verified===true);
    Object.assign(result,{offset:p.offset,image_bytes:p.image_bytes,chip_id:p.chip_id,min_revision:p.min_revision,max_revision:p.max_revision,internal_checksum_verified:true,appended_sha256_verified:true});
    if(result.role==='bootloader'){require(hash(p.region_sha256));result.region_sha256=p.region_sha256;}
    return result;
  });
  // Construct from an allowlist. Never spread the capture record, hardware data,
  // image descriptor strings, file paths, MAC address or private provisioning state.
  return {schema:1,kind:'ampve-browser-review-summary',installable:false,profile:CONTRACT,
    evidence:{source,matching_backup_files:true,independent_capture_record:true,
      current_physical_state_verified:false,
      note:source==='live-browser-capture'?'Two reads completed in this browser session; this export does not re-read the device.':'Files were rehashed locally; independence and device inspection come from an owner-supplied capture record.'},
    backup_sha256:report.sha256,flash_bytes:report.flash_bytes,partition_table_offset:report.partition_table_offset,
    partition_table_md5_verified:true,table_sha256:report.table_sha256,
    stock_layout_matches:report.stock_layout_matches===true,target_slot_erased:report.ota_1_erased===true,
    partitions,images,
    remaining:['Confirm a verified private backup copy on separate storage.',
      'Review the exact stock bootloader and C6 compatibility; P4 flash cannot prove C6 firmware identity.',
      'Compare the actual reviewed candidate and prepare exact private write/recovery regions.',
      'Recheck the connected unit and obtain applicable approval before physical writes.',
      'Validate physical startup, provisioning, recovery and Wi-Fi OTA.']};
}
