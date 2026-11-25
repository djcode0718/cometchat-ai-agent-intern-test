import '@testing-library/jest-dom';

// JSDOM scrollIntoView polyfill
Element.prototype.scrollIntoView = () => {};
