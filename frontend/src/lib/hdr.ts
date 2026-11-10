/** Plain-English words for HDR formats. */

import type { Hdr, MediaSummary } from "@/lib/api";

export const DV = "Dolby Vision";

export type HdrBadgeInfo = { label: string; title: string; tone: "accent" | "neutral" };

/**
 * The short badges for a poster or list row: DV, HDR10+, HDR10, HLG and 4K.
 * HDR10 isn't repeated when Dolby Vision or HDR10+ is already shown.
 */
export function summaryBadges(media: MediaSummary): HdrBadgeInfo[] {
  if (!media.read || media.error) return [];
  const badges: HdrBadgeInfo[] = [];
  const { hdr } = media;
  if (hdr.includes(DV)) {
    badges.push({
      label: "DV",
      title: media.dv_profile ? `Dolby Vision profile ${media.dv_profile}` : "Dolby Vision",
      tone: "accent",
    });
  }
  if (hdr.includes("HDR10+")) badges.push({ label: "HDR10+", title: "HDR10+", tone: "neutral" });
  else if (hdr.includes("HDR10") && !hdr.includes(DV))
    badges.push({ label: "HDR10", title: "HDR10", tone: "neutral" });
  if (hdr.includes("HLG"))
    badges.push({ label: "HLG", title: "HLG (broadcast HDR)", tone: "neutral" });
  if (media.resolution === "4K")
    badges.push({ label: "4K", title: "4K (Ultra HD)", tone: "neutral" });
  return badges;
}

export type HdrExplanation = {
  title: string;
  text: string;
  /** Something the owner should know about (e.g. profile 5 can't be converted). */
  warning?: boolean;
};

/** A heading and a sentence or two explaining the file's picture type. */
export function explainHdr(hdr: Hdr | null): HdrExplanation {
  if (!hdr || hdr.formats.length === 0) {
    return {
      title: "Normal picture (SDR)",
      text: "No HDR. Plays the same on every TV and player.",
    };
  }
  const plus = hdr.formats.includes("HDR10+") ? " It also has HDR10+." : "";
  if (hdr.formats.includes(DV)) {
    const name = `Dolby Vision${hdr.dv_profile ? ` profile ${hdr.dv_profile}` : ""}`;
    if (hdr.dv_profile === "5") {
      return {
        title: name,
        text:
          "Usually from streaming services. There's no HDR10 picture underneath, so TVs and " +
          "players without Dolby Vision show wrong colours (often purple and green). " +
          "Tailarr can't make a copy without Dolby Vision from this file, because there " +
          "would be no correct picture left.",
        warning: true,
      };
    }
    if (hdr.dv_fallback === "HDR10") {
      const disc = hdr.dv_profile === "7" ? " This is the type used on UHD Blu-ray discs." : "";
      const layers = hdr.dv_dual_layer ? " The Dolby Vision part is stored as a second layer." : "";
      return {
        title: `${name} with HDR10`,
        text:
          "There's an HDR10 picture underneath, so TVs and players without Dolby Vision " +
          "show it as HDR10." +
          disc +
          layers +
          plus,
      };
    }
    if (hdr.dv_fallback) {
      return {
        title: `${name} with ${hdr.dv_fallback}`,
        text: `Players without Dolby Vision show the ${hdr.dv_fallback} picture underneath.${plus}`,
      };
    }
    return {
      title: name,
      text: "Tailarr couldn't tell what players without Dolby Vision would show.",
      warning: true,
    };
  }
  if (hdr.formats.includes("HDR10+")) {
    return {
      title: "HDR10+",
      text: "HDR with scene-by-scene brightness information. TVs without HDR10+ show it as HDR10.",
    };
  }
  if (hdr.formats.includes("HDR10")) {
    return { title: "HDR10", text: "The standard HDR format. Works on every HDR TV." };
  }
  return {
    title: "HLG",
    text: "Broadcast-style HDR. Looks normal on TVs without HDR, and brighter on HDR TVs.",
  };
}
