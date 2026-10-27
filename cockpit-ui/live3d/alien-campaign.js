/* SAINTCON 2026 — A.L.I.E.N. ship roster for the PKT Signal Harpoon.
 *
 * Just the bearings/names/codes for the four hulls, so the harpoon can aim at
 * the ship chosen in the fleet-scoring form. The old interactive packet
 * campaign (with its boarding-pass flow) was removed; ships are independent and
 * carry no boarding pass. This module is kept only for that metadata.
 */

export const SHIPS = [
  { code: 'AL01', name: '01 · Navcomputer',     short: '01 NAVCOMPUTER', bearing: -118 },
  { code: 'AL02', name: '02 · Cargo Manifests', short: '02 CARGO HOLD',  bearing: -74 },
  { code: 'AL03', name: '03 · Reactor Core',    short: '03 REACTOR',     bearing: -21 },
  { code: 'AL04', name: '04 · Docking Bay',     short: '04 DOCKING BAY', bearing: 33 },
];
