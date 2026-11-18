import "./studio.css";

export const metadata = { title: "Social Studio · MattMadeMe", description: "MattMadeMe's private social production workspace." };

export default function Layout({ children }) {
  return <html lang="en"><body>{children}</body></html>;
}
