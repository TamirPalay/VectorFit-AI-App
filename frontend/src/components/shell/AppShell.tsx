import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useUser } from "../../context/UserContext";
import { ChartIcon, DumbbellIcon, HomeIcon, ListIcon, UserIcon } from "../icons";
import s from "./AppShell.module.css";

const NAV = [
  { to: "/", label: "Today", Icon: HomeIcon, end: true },
  { to: "/plan", label: "Plan", Icon: DumbbellIcon, end: false },
  { to: "/activity", label: "Activity", Icon: ListIcon, end: false },
  { to: "/progress", label: "Progress", Icon: ChartIcon, end: false },
  { to: "/profile", label: "Profile", Icon: UserIcon, end: true },
];

const initials = (name: string) =>
  name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useUser();

  return (
    <div className={s.app}>
      <header className={s.topbar}>
        <span className={s.brand}>
          <span className={s.mark}>◆</span> VectorFit
        </span>
        {user && (
          <NavLink to="/profile" className={s.who}>
            <span>{user.name}</span>
            <span className={s.avatar}>{initials(user.name)}</span>
          </NavLink>
        )}
      </header>

      <div className={s.shell}>
        <nav className={s.sidebar}>
          <span className={s.brand}>
            <span className={s.mark}>◆</span> VectorFit
          </span>
          {NAV.map(({ to, label, Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `${s.sideItem} ${isActive ? s.active : ""}`}
            >
              <Icon /> {label}
            </NavLink>
          ))}
          {user && (
            <NavLink to="/profile" className={s.who}>
              <span className="row gap-2">
                <span className={s.avatar}>{initials(user.name)}</span>
                {user.name}
              </span>
            </NavLink>
          )}
        </nav>

        <main className={s.main}>{children}</main>
      </div>

      <nav className={s.bottomnav}>
        {NAV.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `${s.navItem} ${isActive ? s.active : ""}`}
          >
            <span className={s.glyph}><Icon /></span>
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
