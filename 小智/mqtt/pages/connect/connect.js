const app = getApp()  //全局变量
var mqtt = require('../../utils/mqtt.js');  //引入mqttjs

Page({
  /**
   * 页面的初始数据
   */
  data: {
      address:"http://124.222.47.162/",
      port:8084,
      path:"/mqtt",
      username:"admin",
      password:"REPLACE_ME",
      tips:''
  },


  AddressInput:function(e){
    this.setData({
      address:e.detail.value,
    })
  },

  PortInput:function(e){
    this.setData({
      port:e.detail.value,
    })
  },

  PathInput:function(e){
    this.setData({
      path:e.detail.value,
    })
  },


  NameInput:function(e){
    this.setData({
      username:e.detail.value,
    })
  },

  PswInput:function(e){
    this.setData({
      password:e.detail.value,
    })
  },

  connectmqtt: function() {
    const options = {
        connectTimeout: 5000, // 增加超时时间到5秒
        clientId: 'wx_' + parseInt(Math.random() * 100 + 800, 10),
        username: this.data.username,
        password: this.data.password,
        reconnect : false,
        protocolVersion: 4, // MQTT 3.1.1
        clean: true,
        keepalive: 60,
        // 添加WebSocket特定选项
        wsOptions: {
            perMessageDeflate: false
        }
    }

    let that = this;
  // 尝试多种连接方式
   var baseUrl = this.data.address.replace(/^https?:\/\//, '').replace(/\/$/, '');
   var ipAddress;

   // 方法1: 尝试WebSocket连接 (ws://)
   console.log('=== 尝试WebSocket连接 ===');
   console.log('服务器:', baseUrl + ':' + this.data.port);
   ipAddress = 'ws://' + baseUrl + ':' + this.data.port + this.data.path;
   console.log('WebSocket URL:', ipAddress);

   // 如果WebSocket失败，尝试方法2: 直接使用http URL让MQTT.js自动转换
   if (this.data.address.includes('http://')) {
     console.log('=== 备选: 使用HTTP URL ===');
     var httpUrl = this.data.address.replace(/\/$/, '') + ':' + this.data.port + this.data.path;
     console.log('HTTP URL (MQTT.js会自动转换):', httpUrl);
     // 可以在这里尝试 httpUrl 如果 ws:// 失败
   }

   console.log('连接选项:', JSON.stringify(options, null, 2));
   //mqtt连接
   app.globalData.client = mqtt.connect(ipAddress, options)
    //连接失败
    app.globalData.client.on('error', (error) => {
        console.log('连接失败:', error)
        this.setData({
          tips:"连接失败"
        })
    })

     //连接成功
    app.globalData.client.on('connect', (e) => {
        console.log('成功连接服务器')
        this.setData({
          tips:"连接成功！"
        })
        //跳转
        wx.switchTab({
          url: '../led/led',
        })
    })
},

})