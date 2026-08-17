/* 打包進頁面的第三方動畫引擎入口。
 *
 * 只 import 真的用到的東西 —— esbuild 會 tree-shake,沒用到的不會進 bundle。
 * 打包結果由 scripts/build.py 內嵌進 public/index.html,所以**執行時仍然
 * 零外部請求**:瀏覽器不會去任何 CDN 拿東西,離線也能開,CSP 也不用開洞。
 *
 * 為什麼是這兩個而不是別的(星數與授權都是 gh api 當場查的):
 *   anime.js  72,216★ MIT  —— 動畫引擎;v4 自帶 onScroll,所以不需要再加一個捲動庫
 *   lenis     15,455★ MIT  —— 慣性平滑捲動
 * 評估過但沒用的:motion 33,266★ MIT(光 scroll 就 75KB,能力與 anime.js 重疊)、
 * animate.css 82,737★(Hippocratic 2.1,非 OSI 授權)、Hover.css 29,397★(商用需付費)。
 * 完整出處見 THIRD-PARTY.md。
 */
import { animate, createTimeline, utils, stagger } from 'animejs';
import Lenis from 'lenis';

// 捲動觸發用原生 IntersectionObserver,不進 anime 的 onScroll —— 少 12KB,
// 而且退路(引擎沒載到時卡片仍然看得見)比較好寫。
window.WP = { anime: { animate, createTimeline, utils, stagger }, Lenis };
