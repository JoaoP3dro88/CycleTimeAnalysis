/**
 * roiTracker.js
 *
 * Pure logic for ROI entry/exit detection — no React, no DOM.
 *
 * Constants:
 *   CONFIRMATION_FRAMES = 1   consecutive frames to confirm entry (was 3 — reduces entry delay)
 *   GRACE_FRAMES        = 3   frames of hand absence before confirming exit (was 10)
 *   GRACE_MS            = 80  ms of video-time before confirming exit (was 333ms ≈ 10 frames)
 *
 * Delay analysis (previous values → current):
 *   Entry delay:  3 frames → 1 frame  (~66ms at 30fps saved)
 *   Exit  delay:  333ms    → 80ms     (~253ms saved, ~2-3 frames at 30fps)
 *   startFrame is now stored at ENTRY time (not back-calculated from duration)
 *   endFrame   is corrected to exclude the grace period
 */

export const CONFIRMATION_FRAMES = 1
export const GRACE_FRAMES = 3
// Grace period in ms — used when a video-time timestamp is provided.
export const GRACE_MS = 80

/**
 * Point-in-polygon test (ray casting) for normalised [0,1] coords.
 * @param {number} px
 * @param {number} py
 * @param {{x:number,y:number}[]} polygon
 * @returns {boolean}
 */
export function pointInPolygon(px, py, polygon) {
  let inside = false
  const n = polygon.length
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = polygon[i].x, yi = polygon[i].y
    const xj = polygon[j].x, yj = polygon[j].y
    const intersect =
      yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
  }
  return inside
}

/**
 * Find which ROI (if any) contains the given normalised point.
 * Returns the ROI index or null.
 * @param {number} px
 * @param {number} py
 * @param {Array<{name:string, points:{x:number,y:number}[]}>} rois
 * @returns {number|null}
 */
export function detectRoi(px, py, rois) {
  for (let i = 0; i < rois.length; i++) {
    if (rois[i].points.length >= 3 && pointInPolygon(px, py, rois[i].points)) {
      return i
    }
  }
  return null
}

/**
 * Create a fresh per-hand buffer state object.
 */
function makeHandState() {
  return {
    currentRoi: null,      // confirmed ROI index the hand is currently in
    buffer: [],            // pending entry confirmation buffer
    lostFrames: 0,         // consecutive frames where hand was absent
    lostSince: null,       // timestamp (ms) when hand was first lost
    entryTime: null,       // timestamp (ms) when hand entered currentRoi
    entryFrame: null,      // frame number when hand entered currentRoi (precise start)
  }
}

/**
 * RoiTracker — stateful class mirroring VideoProcessor's confirmation logic.
 *
 * Usage:
 *   const tracker = new RoiTracker()
 *   // each frame:
 *   const events = tracker.processFrame(handsDetected, rois)
 *   // handsDetected: { Left: roiIndex|null, Right: roiIndex|null }
 *   //   (only include keys for hands that were actually detected this frame)
 */
export class RoiTracker {
  constructor() {
    this.state = {
      Left: makeHandState(),
      Right: makeHandState(),
    }
    this.eventLog = []
  }

  reset() {
    this.state = { Left: makeHandState(), Right: makeHandState() }
    this.eventLog = []
  }

  /**
   * @param {{ Left?: number|null, Right?: number|null }} handsDetected
   *   Keys present = hand was detected this frame. Missing key = hand absent.
   * @param {Array} rois  ROI definitions (needed for names)
   * @param {number} [nowOverride]  Optional timestamp in ms to use instead of Date.now().
   *   Pass video.currentTime * 1000 when processing video frames so duration
   *   is in video-time seconds (correct at any playback speed).
   * @param {number} [currentFrame]  Current video frame number. When provided,
   *   is stored at entry and returned in EXIT events as entryFrame/exitFrame
   *   so the caller can build exact start_frame/end_frame without back-calculating.
   * @returns {Array}  New events produced this frame
   */
  processFrame(handsDetected, rois, nowOverride, currentFrame) {
    const now = nowOverride ?? Date.now()
    const newEvents = []

    for (const handLabel of ['Left', 'Right']) {
      const buf = this.state[handLabel]
      const isDetected = handLabel in handsDetected
      const detectedRoi = handsDetected[handLabel] ?? null

      if (!isDetected) {
        // ── Hand absent ──────────────────────────────────────────────────────
        buf.lostFrames++
        if (buf.lostSince === null) buf.lostSince = now

        const graceExpired = (now - buf.lostSince) > GRACE_MS

        if (graceExpired && buf.currentRoi !== null) {
          // Grace period expired → confirm exit.
          // Duration = time from entry to when hand was FIRST lost (lostSince),
          // NOT to now — this removes the grace-period inflation from the duration.
          const exitTime = buf.lostSince   // hand was last seen at this time
          const duration = (exitTime - buf.entryTime) / 1000
          const ev = {
            type: 'EXIT',
            hand: handLabel,
            roiIndex: buf.currentRoi,
            roiName: rois[buf.currentRoi]?.name ?? `ROI ${buf.currentRoi}`,
            duration: Math.max(0, duration),
            timestamp: now,
            entryFrame: buf.entryFrame,   // exact frame when entry was confirmed
            lostFrame: buf.lostFrame,     // exact frame when hand was first lost
          }
          newEvents.push(ev)
          this.eventLog.push(ev)
          buf.currentRoi = null
          buf.entryTime = null
          buf.entryFrame = null
          buf.lostSince = null
          buf.lostFrame = null
          buf.lostFrames = 0
          buf.buffer = []
        } else if (buf.lostFrame == null && currentFrame != null) {
          // Record the first frame the hand went missing (for end_frame correction)
          buf.lostFrame = currentFrame
        }
        continue
      }

      // ── Hand detected ────────────────────────────────────────────────────
      buf.lostFrames = 0
      buf.lostSince = null
      buf.lostFrame = null

      // Changed ROI (including moving to null = outside all ROIs)
      if (buf.currentRoi !== null && buf.currentRoi !== detectedRoi) {
        const duration = (now - buf.entryTime) / 1000
        if (duration >= 0.15) {
          const ev = {
            type: 'EXIT',
            hand: handLabel,
            roiIndex: buf.currentRoi,
            roiName: rois[buf.currentRoi]?.name ?? `ROI ${buf.currentRoi}`,
            duration,
            timestamp: now,
            entryFrame: buf.entryFrame,
            lostFrame: currentFrame ?? null,
          }
          newEvents.push(ev)
          this.eventLog.push(ev)
        }
        buf.currentRoi = null
        buf.entryTime = null
        buf.entryFrame = null
        buf.lostSince = null
        buf.lostFrame = null
        buf.buffer = []
      }

      // Accumulate entry confirmation
      if (detectedRoi !== null && buf.currentRoi === null) {
        buf.buffer.push({ roi: detectedRoi, frame: currentFrame ?? null })

        // Keep only the last N frames
        if (buf.buffer.length > CONFIRMATION_FRAMES * 3) {
          buf.buffer = buf.buffer.slice(-CONFIRMATION_FRAMES * 3)
        }

        // Count consecutive matching entries at the tail
        const tail = buf.buffer.slice(-CONFIRMATION_FRAMES)
        const confirmed = tail.length === CONFIRMATION_FRAMES && tail.every((v) => v.roi === detectedRoi)

        if (confirmed) {
          buf.currentRoi = detectedRoi
          buf.entryTime = now
          // Use the frame of the FIRST entry in the confirmation window
          // so start_frame points to when the hand actually entered, not
          // when confirmation was achieved.
          buf.entryFrame = tail[0].frame
          buf.buffer = []

          const ev = {
            type: 'ENTRY',
            hand: handLabel,
            roiIndex: detectedRoi,
            roiName: rois[detectedRoi]?.name ?? `ROI ${detectedRoi}`,
            timestamp: now,
            entryFrame: buf.entryFrame,
          }
          newEvents.push(ev)
          this.eventLog.push(ev)
        }
      }
    }

    return newEvents
  }
}
