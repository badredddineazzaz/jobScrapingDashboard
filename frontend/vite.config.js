import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), "");
    const apiUrl = env.VITE_API_URL || "http://localhost:8001";
    return {
        plugins: [react()],
        server: {
            port: Number(env.VITE_DEV_SERVER_PORT || 5173),
            proxy: {
                "/api": {
                    target: apiUrl,
                    changeOrigin: true,
                },
            },
        },
    };
});
