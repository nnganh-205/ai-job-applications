import { useEffect, useRef } from "react";

// Scroll work stays in one animation frame; React does not rerender on scroll.
export default function useLandingMotion() {
  const root = useRef(null);
  useEffect(() => {
    const page = root.current;
    if (!page) return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    const sections = [...page.querySelectorAll("[data-reveal]")];
    const mail = page.querySelector(".zen-letter");
    const ending = page.querySelector(".zen-ending");
    const laptop = page.querySelector(".zen-laptop-stage");
    const clamp = (value) => Math.min(1, Math.max(0, value));
    const update = () => {
      frame = 0;
      if (preference.matches) {
        page.style.setProperty("--hero-scroll", 0);
        page.style.setProperty("--letter-progress", 1);
        page.style.setProperty("--ending-progress", 1);
      }
      page.style.setProperty(
        "--hero-scroll",
        preference.matches ? 0 : clamp(window.scrollY / 900),
      );
      if (mail && !preference.matches)
        page.style.setProperty(
          "--letter-progress",
          clamp(
            (window.innerHeight * 0.8 - mail.getBoundingClientRect().top) /
              (window.innerHeight * 0.7),
          ),
        );
      if (ending && !preference.matches)
        page.style.setProperty(
          "--ending-progress",
          clamp(
            (window.innerHeight - ending.getBoundingClientRect().top) /
              window.innerHeight,
          ),
        );
      if (laptop) {
        const scale = Math.min(1, (laptop.clientWidth - 32) / 640);
        const track = laptop.querySelector(".zen-laptop-scroll-track");
        // Match the reference: 750px scroll, enlargement over the first 30%,
        // flattening between 10–30%, and continuous travel to the hands.
        const progress = preference.matches
          ? 1
          : clamp(-track.getBoundingClientRect().top / (750 * scale));
        const enlarge = clamp(progress / 0.3);
        const flatten = clamp((progress - 0.1) / 0.2);
        laptop.style.setProperty("--laptop-scale", scale);
        // The final 520px sheet is centered on the stage. Its start uses
        // the screen's own perspective and clipping, so it cannot cover fields.
        laptop.style.setProperty(
          "--cv-x",
          `${343.2 * enlarge}px`,
        );
        laptop.style.setProperty("--cv-y", `${1002.5 * progress}px`);
        laptop.style.setProperty("--cv-scale", 1 + 1.6 * enlarge);
        laptop.style.setProperty("--cv-rotate", `${-25 + 25 * flatten}deg`);
        laptop.style.setProperty(
          "--cv-clip",
          `${-500 * clamp(progress / 0.1)}px`,
        );
      }
    };
    const queue = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    let observer;
    if ("IntersectionObserver" in window) {
      observer = new IntersectionObserver(
        (entries) => {
          entries.forEach(({ target, isIntersecting }) => {
            if (isIntersecting) {
              target.classList.add("is-visible");
              observer.unobserve(target);
            }
          });
        },
        { threshold: 0.08 },
      );
      sections.forEach((section) => observer.observe(section));
      page.dataset.motion = "ready";
    }
    window.addEventListener("scroll", queue, { passive: true });
    window.addEventListener("resize", queue);
    preference.addEventListener("change", queue);
    update();
    return () => {
      observer?.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", queue);
      window.removeEventListener("resize", queue);
      preference.removeEventListener("change", queue);
    };
  }, []);
  return root;
}
