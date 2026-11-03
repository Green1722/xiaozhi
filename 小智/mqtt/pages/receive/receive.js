//index.js
//获取应用实例
const app = getApp()
var mqtt = require('../../utils/mqtt.js');

Page({
  data: {
    humidity:0,
    temperature:0,
    date:null
  },
  onLoad: function() {
    this.initSocket();
  },
  //接收信息函数
  initSocket: function() {
   
    var that=this;
    app.globalData.client.subscribe('classroom/response');
    app.globalData.client.subscribe('classroom/status');
    app.globalData.client.on('message', function(topic, payload) {
      try {
        var receive = JSON.parse(payload);
        var time = new Date();
        var timeStr = time.getHours() + ":" + time.getMinutes() + ":" + time.getSeconds();

        console.log('收到消息:', topic, receive); // 添加调试日志

        // 根据主题和消息内容进行不同处理
        if (topic === 'classroom/status') {
          // 处理设备状态消息
          if (receive.temperature !== undefined && receive.humidity !== undefined) {
            // 温湿度传感器数据
            that.setData({
              temperature: receive.temperature,
              humidity: receive.humidity,
              date: timeStr
            });
          }
          // 可以在这里添加其他设备状态的处理
        } else if (topic === 'classroom/response') {
          // 处理响应消息
          if (receive.temperature !== undefined && receive.humidity !== undefined) {
            // 如果响应消息包含传感器数据，也更新显示
            that.setData({
              temperature: receive.temperature,
              humidity: receive.humidity,
              date: timeStr
            });
          }
          // 可以在这里添加命令执行结果的处理
        }
      } catch (e) {
        console.error('解析消息失败:', e, payload);
      }
    })
    }


  
  
})

