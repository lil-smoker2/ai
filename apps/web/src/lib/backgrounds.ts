/** Background pictures for the app shell, one per section.
 *
 * The picture is only ever a backdrop: it shows in the gutters either side of
 * the centred content column, in the gaps between cards, and below the last
 * card. Everything that carries text - .card, .sidebar, .topbar, .stat-card -
 * keeps a solid background, and a wash of --bg sits over the picture so a
 * heading never has to compete with the artwork behind it.
 *
 * The source images are small (236-414px wide), so `cover` scales them up
 * substantially on a desktop window. Under the wash that reads as a soft tint
 * rather than a pixelated photo; swapping in larger files under the same names
 * is all it takes to make them crisp.
 */
import peacockPaper from "../assets/backgrounds/peacock-paper.jpg";
import redSpace from "../assets/backgrounds/red-space.jpg";
import sageAbstract from "../assets/backgrounds/sage-abstract.jpg";
import schoolFrame from "../assets/backgrounds/school-frame.jpg";
import blueWater from "../assets/backgrounds/blue-water.jpg";

/** Home, Inventory, Images, Shopping, Tasks, Notifications, Settings and
 * Onboarding get this one, as do any routes added later. */
export const DEFAULT_BACKGROUND = sageAbstract;

/** Keyed by the segment after /app, matching AppShell's NAV_ITEMS paths. */
const BACKGROUND_BY_SECTION: Record<string, string> = {
  money: sageAbstract,
  "earnings-savings": sageAbstract,
  networth: sageAbstract,
  reports: blueWater,
  goals: peacockPaper,
  student: schoolFrame,
  assistant: redSpace,
};

/** The section a path belongs to: "/app/goals/3" -> "goals". Anything outside
 * the shell, including a bare "/app", has no section of its own. */
export function sectionForPath(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  return parts[0] === "app" ? (parts[1] ?? "") : "";
}

export function backgroundForPath(pathname: string): string {
  return BACKGROUND_BY_SECTION[sectionForPath(pathname)] ?? DEFAULT_BACKGROUND;
}
