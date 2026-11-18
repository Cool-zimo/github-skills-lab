const path = require('path');

module.exports = {
    mode: 'development',
    target: 'web',
    devtool: 'cheap-module-source-map',
    entry: {
        player: './player/index.js'
    },
    output: {
        path: path.resolve(__dirname, 'player', 'dist'),
        filename: 'player.js',
        publicPath: '/dist/',
        libraryTarget: 'umd'
    },
    node: {
        fs: 'empty'
    },
    module: {
        rules: [
            {
                test: /\.js$/,
                loader: 'babel-loader',
                include: path.resolve(__dirname, 'src'),
                query: {presets: [['@babel/preset-env']]}
            },
            {
                test: /\.mp3$/,
                loader: 'file-loader',
                options: {name: 'media/[name].[ext]'}
            }
        ]
    },
    performance: {hints: false}
};
