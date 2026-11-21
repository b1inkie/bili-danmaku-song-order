"""Pure UI simulator regression, no network/filesystem/process update operations."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UpdatePreviewTests(unittest.TestCase):
    def test_state_machine_timing_cancel_failures_and_rollback(self):
        script = r'''
const assert = require('assert');
const {UpdatePreviewModel: Model} = require('./web/update-preview.js');
class Clock {
 constructor(){this.now=0;this.seq=0;this.jobs=new Map()}
 setTimeout(fn,delay){const id=++this.seq;this.jobs.set(id,{fn,at:this.now+delay,repeat:0});return id}
 setInterval(fn,delay){const id=++this.seq;this.jobs.set(id,{fn,at:this.now+delay,repeat:delay});return id}
 clearTimeout(id){this.jobs.delete(id)} clearInterval(id){this.jobs.delete(id)}
 advance(ms){const end=this.now+ms;let loops=0;while(true){
  const next=[...this.jobs].filter(([id,j])=>j.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;
  assert(++loops<10000);const [id,job]=next;this.now=job.at;
  if(job.repeat)job.at+=job.repeat;else this.jobs.delete(id);job.fn();
 }this.now=end}
}
const clock=new Clock(),events=[],m=new Model(s=>events.push(s),clock);
m.start();m.start();assert.equal(clock.jobs.size,1);
clock.advance(4999);assert.equal(m.state.phase,'idle');clock.advance(1);assert.equal(m.state.phase,'checking');
clock.advance(750);assert.equal(m.state.phase,'available');assert(m.state.available);
const checked=events.filter(e=>e.phase==='checking').length;
clock.advance(Model.CHECK_INTERVAL_MS-750);assert.equal(m.state.phase,'checking');
assert.equal(events.filter(e=>e.phase==='checking').length,checked+1);clock.advance(750);
m.download();clock.advance(360);assert.equal(m.state.progress,20);m.cancel();
clock.advance(5000);assert.equal(m.state.phase,'available');assert.equal(m.state.progress,0);
m.scenario='download-error';m.download();clock.advance(1500);assert.equal(m.state.phase,'download-error');
m.scenario='available';m.download();clock.advance(1800);assert.equal(m.state.phase,'verifying');
clock.advance(650);assert.equal(m.state.phase,'ready');assert(m.state.available);
m.check();assert.equal(m.state.phase,'ready');m.install();assert.equal(m.state.phase,'installing');
clock.advance(900);assert.equal(m.state.phase,'complete');assert.equal(m.state.current,'0.2.0');
assert.equal(m.state.backup,'0.1.0');assert(!m.state.available);
m.rollback();assert.equal(m.state.current,'0.1.0');assert.equal(m.state.backup,null);
m.scenario='latest';m.check();clock.advance(750);assert.equal(m.state.phase,'latest');assert(!m.state.available);
m.scenario='check-error';m.check();clock.advance(750);assert.equal(m.state.phase,'check-error');assert(!m.state.available);
m.scenario='available';m.check();clock.advance(750);assert(m.state.available);
m.scenario='check-error';m.check();clock.advance(750);assert(m.state.available); // cached result, not invented on failure
m.reset();assert.equal(m.state.phase,'idle');assert(!m.state.available);
m.stop();assert.equal(clock.jobs.size,0);
'''
        result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_preview_module_has_no_actual_update_io(self):
        source = (ROOT / 'web/update-preview.js').read_text('utf-8')
        for forbidden in ('fetch(', 'XMLHttpRequest', 'window.pywebview.api', 'localStorage.',
                          'location.reload(', 'location.href =', 'window.close(', 'child_process'):
            self.assertNotIn(forbidden, source)
        self.assertIn('has("preview")', source)


if __name__ == '__main__':
    unittest.main()
