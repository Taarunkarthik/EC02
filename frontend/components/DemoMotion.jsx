import { useEffect, useRef } from 'react';
import { animate } from 'motion/react';
import './DemoMotion.css';

const stages = [
  ['scanning', 'Scanning source…', 'RUNNING', false],
  ['diagnostic', 'Division by zero · line 08', 'DIAGNOSTIC', false],
  ['fixing', 'Guard the empty input.', 'APPLYING FIX', true],
  ['testing', 'Running the sample tests…', 'TESTING', true],
  ['passed', 'All checks passed. Exit code: 0', 'PASSED', true],
];
const DURATION = 3000;

// An isolated illustration controller: never reads or writes competition state.
export default function DemoMotion({ target }) {
  const scanRef = useRef(null);
  const progressRef = useRef(null);
  useEffect(() => {
    const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
    const button = target.querySelector('#demo-toggle');
    const code = target.querySelector('.demo-code');
    const bug = target.querySelector('#demo-bug-line');
    const value = target.querySelector('#demo-return-value');
    const status = target.querySelector('#demo-status');
    const badge = target.querySelector('#demo-status-badge');
    const indicator = target.querySelector('#demo-line-indicator');
    const problems = target.querySelector('#demo-problem-count');
    const scan = scanRef.current, progress = progressRef.current;
    let index = motionQuery.matches ? 4 : 0;
    let userPaused = motionQuery.matches, visible = true, running = false, alive = true;
    let timer = 0, remaining = DURATION, started = 0, generation = 0, resizeFrame = 0;
    let controls = [];
    const allowed = () => alive && visible && !document.hidden && !userPaused;
    const stopAnimations = () => { controls.forEach(control => control.stop()); controls = []; };
    function motion(element, frames, options) {
      if (motionQuery.matches) return null;
      const control = animate(element, frames, options);
      controls.push(control);
      if (!allowed()) control.pause();
      return control;
    }
    function position() {
      const frame = target.getBoundingClientRect();
      const first = code.firstElementChild.getBoundingClientRect();
      const last = code.lastElementChild.getBoundingClientRect();
      const fault = bug.getBoundingClientRect();
      scan.style.height = `${first.height}px`;
      progress.style.top = `${target.querySelector('.demo-console').getBoundingClientRect().top-frame.top}px`;
      return { first:first.top-frame.top, last:last.top-frame.top, fault:fault.top-frame.top };
    }
    function paint(animateTransition = true) {
      const own = ++generation;
      stopAnimations();
      const [name, label, state, fixed] = stages[index];
      target.dataset.demoStage = name;
      status.textContent = label;
      badge.textContent = state;
      badge.classList.toggle('is-success', name === 'passed');
      bug.classList.toggle('is-fixed', fixed);
      indicator.textContent = fixed ? '✓' : '!';
      problems.textContent = fixed ? '0' : '1';
      value.textContent = fixed ? '0' : 'total / count';
      value.style.opacity = '1'; value.style.transform = 'none';
      const points = position();
      const from = name === 'scanning' || name === 'testing' ? points.first : points.fault;
      const to = name === 'scanning' || name === 'testing' ? points.last : points.fault;
      scan.style.transform = `translateY(${from}px)`;
      scan.style.opacity = name === 'passed' ? '0' : '1';
      progress.style.transform = name === 'passed' ? 'scaleX(1)' : 'scaleX(0)';
      if (motionQuery.matches) return;
      if (animateTransition) motion(status, {opacity:[0,1],transform:['translateY(4px)','translateY(0px)']}, {duration:.28,ease:'easeOut'});
      if (name !== 'passed') {
        motion(progress, {transform:['scaleX(0)','scaleX(1)']}, {duration:remaining/1000,ease:'linear'});
        if (from !== to) motion(scan, {transform:[`translateY(${from}px)`,`translateY(${to}px)`]}, {duration:remaining/1000,ease:'linear'});
        else motion(scan, {opacity:[.35,.9,.35]}, {duration:1.3,repeat:Infinity,ease:'easeInOut'});
      }
      if (name === 'fixing' && animateTransition) {
        value.textContent = 'total / count';
        const fade = motion(value, {opacity:[1,0],transform:['translateY(0px)','translateY(-3px)']}, {duration:.24,ease:'easeIn'});
        fade?.then(() => {
          if (!alive || generation !== own) return;
          value.textContent = '0';
          motion(value, {opacity:[0,1],transform:['translateY(4px)','translateY(0px)']}, {duration:.38,ease:'easeOut'});
        });
      }
      if (name === 'passed') motion(indicator, {opacity:[.2,1]}, {duration:.5,ease:'easeOut'});
    }
    function advance() {
      if (!allowed()) return;
      index = (index+1)%stages.length;
      remaining = DURATION;
      paint();
      started = performance.now();
      timer = setTimeout(advance, remaining);
    }
    function sync() {
      const next = allowed();
      target.dataset.demoPaused = String(!next);
      document.documentElement.dataset.demoPaused = String(!next);
      button.textContent = userPaused ? 'Play demo' : 'Pause demo';
      button.setAttribute('aria-pressed', String(userPaused));
      button.setAttribute('aria-label', userPaused ? 'Play demonstration' : 'Pause demonstration');
      if (next === running) return;
      if (next) {
        controls.forEach(control=>control.play());
        started = performance.now();
        timer = setTimeout(advance, Math.max(0,remaining));
      } else {
        clearTimeout(timer);
        remaining = Math.max(0,remaining-(performance.now()-started));
        controls.forEach(control=>control.pause());
      }
      running = next;
    }
    const toggle = () => { userPaused = !userPaused; sync(); };
    const motionChange = () => {
      clearTimeout(timer); running = false; remaining = DURATION;
      userPaused = motionQuery.matches;
      if (userPaused) index = 4;
      paint(false); sync();
    };
    const observer = new IntersectionObserver(([entry]) => {visible=entry.isIntersecting;sync();}, {threshold:.1});
    observer.observe(target);
    const resize = new ResizeObserver(() => {
      cancelAnimationFrame(resizeFrame);
      resizeFrame=requestAnimationFrame(() => {
        // Reposition overlays only; reading geometry happens on resize, never each frame.
        const points=position();
        if (index===1 || index===2) scan.style.transform=`translateY(${points.fault}px)`;
      });
    });
    resize.observe(target);
    button.addEventListener('click',toggle);
    document.addEventListener('visibilitychange',sync);
    motionQuery.addEventListener('change',motionChange);
    paint(false); sync();
    return () => {
      alive=false; ++generation; clearTimeout(timer); cancelAnimationFrame(resizeFrame); stopAnimations();
      observer.disconnect();resize.disconnect();button.removeEventListener('click',toggle);
      document.removeEventListener('visibilitychange',sync);motionQuery.removeEventListener('change',motionChange);
    };
  }, [target]);
  return <><div ref={scanRef} className="demo-scan-cursor" /><div ref={progressRef} className="demo-run-progress" /></>;
}
