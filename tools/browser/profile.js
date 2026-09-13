// The same checked-in contract generates native constants and backend eligibility.
import profile from '../../firmware/profiles/waveshare-7b-stock-v1.json';

export const HARDWARE_PROFILE=profile;
export const CONTRACT={profile_id:profile.id,profile_version:profile.version,
  layout_id:profile.layout.id,firmware_lineage:profile.firmware_lineage};
export const PARTITIONS=Object.fromEntries(profile.layout.partitions.map(p=>[p.name,p]));
export function matchesContract(value) {
  return value!==null && typeof value==='object' && Object.keys(value).length===Object.keys(CONTRACT).length &&
    Object.entries(CONTRACT).every(([key,expected])=>value[key]===expected);
}
