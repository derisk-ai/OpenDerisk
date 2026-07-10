/** @type {import("jest").Config }**/
module.exports = {
  testEnvironment: "node",
  preset: "ts-jest",
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  testMatch: [
    "<rootDir>/src/**/__tests__/**/*.test.ts",
    "<rootDir>/src/**/__tests__/**/*.test.tsx",
  ],
  // Project tsconfig uses jsx: "preserve"; override to react-jsx so ts-jest can
  // transpile .tsx React tests into executable JS under Node/jsdom.
  transform: {
    "^.+\\.tsx?$": ["ts-jest", { tsconfig: { jsx: "react-jsx" } }],
  },
  // Registers @testing-library/jest-dom matchers (toBeInTheDocument, …) for
  // React component tests that run under the jsdom environment.
  setupFilesAfterEnv: ["<rootDir>/src/test-setup.ts"],
};