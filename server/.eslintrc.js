module.exports = {
  env: {
    node: true,
    es2021: true,
  },
  ignorePatterns: ['build/*'],
  extends: [
    'plugin:@typescript-eslint/eslint-recommended',
    'plugin:@typescript-eslint/recommended',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 12,
    sourceType: 'module',
  },
  plugins: ['@typescript-eslint'],
  rules: {
    quotes: ['error', 'single'],
    semi: ['error', 'always'],
    'comma-dangle': ['error', 'always-multiline'],
    indent: ['error', 2],
    '@typescript-eslint/no-explicit-any': 0,
  },
};
