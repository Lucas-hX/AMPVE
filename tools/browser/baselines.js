// Recognition is local and deterministic. It is never publisher authorization.
import catalog from '../../firmware/profiles/stock-baselines.json';
import {CONTRACT} from './profile.js';

export function recognizeBaseline(report) {
  if(report?.stock_layout_matches!==true || report.partition_table_md5_verified!==true || report.matching_files!==true)return null;
  const boot=report.images?.find(image=>image.name==='bootloader');
  if(boot?.internal_checksum_verified!==true || boot.appended_sha256_verified!==true)return null;
  return catalog.baselines.find(baseline=>baseline.profile_id===CONTRACT.profile_id && baseline.regions.every(region=>
    region.name==='bootloader'?boot.offset===region.offset && boot.region_sha256===region.sha256:
    region.name==='table'?report.partition_table_offset===region.offset && report.table_sha256===region.sha256:false))?.id || null;
}
