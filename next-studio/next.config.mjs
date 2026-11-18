const hosted = process.env.STUDIO_HOSTED === "1";

export default {
  poweredByHeader: false,
  basePath: hosted ? "/studio" : "",
  skipTrailingSlashRedirect: hosted,
  env: { NEXT_PUBLIC_STUDIO_HOSTED: hosted ? "1" : "0" },
  experimental: { cpus: 2 },
};
