/**
 * roslib browser wrapper
 *
 * The roslib npm package uses `this.ROSLIB` in its source which breaks
 * in Vite's ESM strict mode (where `this` is undefined). The pre-built
 * browser bundle (roslib/build/roslib.js) sets window.ROSLIB as a global.
 * We import that bundle for its side-effect and re-export the global.
 */
import 'roslib/build/roslib.js'

var ROSLIB = window.ROSLIB

export default ROSLIB
